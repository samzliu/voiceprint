export const HOSTED_MIN_WORDS = 1_000;
export const HOSTED_RECOMMENDED_WORDS = 2_000;
const MIN_CHUNK_WORDS = 25;
const TARGET_CHUNK_WORDS = 250;

export type CorpusDocument = { name: string; text: string };

export type CorpusChunk = {
  source: string;
  text: string;
  words: number;
  length: "short" | "medium" | "long";
};

export type CorpusReadiness = {
  status: "blocked" | "warning" | "ready";
  ready: boolean;
  documents: number;
  usable_documents: number;
  raw_words: number;
  usable_words: number;
  chunks: number;
  duplicate_chunks: number;
  duplicate_words: number;
  minimum_words: number;
  recommended_words: number;
  reasons: string[];
  warnings: string[];
};

function words(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

function proseOnly(markdown: string): string {
  const withoutFrontmatter = markdown.replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, "");
  const withoutCode = withoutFrontmatter.replace(/```[\s\S]*?```/g, "");
  const lines = withoutCode.split(/\r?\n/);
  const kept: string[] = [];
  let inTable = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (/^#{1,6}\s/.test(trimmed) || /^>/.test(trimmed)) continue;
    if (/^\|.*\|$/.test(trimmed)) {
      inTable = true;
      continue;
    }
    if (inTable && !trimmed) {
      inTable = false;
      kept.push("");
      continue;
    }
    if (inTable) continue;
    kept.push(line);
  }
  return kept.join("\n").trim();
}

function isProseParagraph(paragraph: string): boolean {
  const lines = paragraph.split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length || !/[.!?]/.test(paragraph)) return false;
  const listLines = lines.filter((line) => /^\s*(?:[-*+•]|\d+[.)])\s/.test(line)).length;
  return listLines / lines.length <= 0.4;
}

function splitDocument(text: string): string[] {
  const paragraphs = proseOnly(text)
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(isProseParagraph);
  if (!paragraphs.length) return [];
  if (paragraphs.reduce((total, paragraph) => total + words(paragraph), 0) <= 120) {
    return [paragraphs.join("\n\n")];
  }

  const chunks: string[] = [];
  let buffer: string[] = [];
  let bufferWords = 0;
  for (const paragraph of paragraphs) {
    const paragraphWords = words(paragraph);
    if (buffer.length && bufferWords + paragraphWords > TARGET_CHUNK_WORDS) {
      chunks.push(buffer.join("\n\n"));
      buffer = [];
      bufferWords = 0;
    }
    buffer.push(paragraph);
    bufferWords += paragraphWords;
  }
  if (buffer.length) chunks.push(buffer.join("\n\n"));
  return chunks;
}

function fingerprint(text: string): string {
  return text.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function lengthBucket(count: number): "short" | "medium" | "long" {
  if (count <= 120) return "short";
  if (count <= 500) return "medium";
  return "long";
}

export function prepareCorpus(documents: CorpusDocument[]): {
  report: CorpusReadiness;
  chunks: CorpusChunk[];
} {
  const chunks: CorpusChunk[] = [];
  const seen = new Set<string>();
  const usableSources = new Set<string>();
  let duplicateChunks = 0;
  let duplicateWords = 0;

  for (const document of documents) {
    for (const text of splitDocument(document.text)) {
      const count = words(text);
      if (count < MIN_CHUNK_WORDS) continue;
      const key = fingerprint(text);
      if (seen.has(key)) {
        duplicateChunks += 1;
        duplicateWords += count;
        continue;
      }
      seen.add(key);
      usableSources.add(document.name);
      chunks.push({ source: document.name, text, words: count, length: lengthBucket(count) });
    }
  }

  const usableWords = chunks.reduce((total, chunk) => total + chunk.words, 0);
  const rawWords = documents.reduce((total, document) => total + words(document.text), 0);
  const reasons: string[] = [];
  const warnings: string[] = [];
  if (!documents.length) reasons.push("No readable documents were found.");
  if (usableWords < HOSTED_MIN_WORDS) {
    reasons.push(
      `Only ${usableWords} usable words were found; at least ${HOSTED_MIN_WORDS} are required.`,
    );
  } else if (usableWords < HOSTED_RECOMMENDED_WORDS) {
    warnings.push(
      `${usableWords} usable words passed, but ${HOSTED_RECOMMENDED_WORDS}+ usually produces a stronger voice.`,
    );
  }
  if (duplicateChunks) {
    warnings.push(
      `Removed ${duplicateChunks} duplicate passage${duplicateChunks === 1 ? "" : "s"} totaling ${duplicateWords} words.`,
    );
  }
  const ignored = documents.length - usableSources.size;
  if (ignored) {
    warnings.push(
      `Ignored ${ignored} document${ignored === 1 ? "" : "s"} without a usable prose passage of ${MIN_CHUNK_WORDS}+ words.`,
    );
  }
  const status = reasons.length ? "blocked" : warnings.length ? "warning" : "ready";

  return {
    chunks,
    report: {
      status,
      ready: status !== "blocked",
      documents: documents.length,
      usable_documents: usableSources.size,
      raw_words: rawWords,
      usable_words: usableWords,
      chunks: chunks.length,
      duplicate_chunks: duplicateChunks,
      duplicate_words: duplicateWords,
      minimum_words: HOSTED_MIN_WORDS,
      recommended_words: HOSTED_RECOMMENDED_WORDS,
      reasons,
      warnings,
    },
  };
}
