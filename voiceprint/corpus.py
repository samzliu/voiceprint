"""Getting someone's writing in: files, folders, or piped text -> chunks.

Chunking targets ~250 words on paragraph boundaries, with one deliberate
exception: a document that is already short stays whole. A 60-word email is a
real sample of how someone writes short things, and merging it into a 250-word
block would destroy exactly the signal the `short` length control needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from voiceprint import markdown
from voiceprint.scaffold import SHORT_MAX_WORDS, length_bucket

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".mdx"}
TARGET_WORDS = 250
MIN_CHUNK_WORDS = 25
MIN_CORPUS_WORDS = 300
WEAK_CORPUS_WORDS = 700
HOSTED_MIN_CORPUS_WORDS = 1_000
HOSTED_RECOMMENDED_CORPUS_WORDS = 2_000

LIST_LINE = re.compile(r"^\s*([-*+•]|\d+[.)])\s")
SENTENCE_END = re.compile(r"[.!?]")
MAX_LIST_SHARE = 0.4


@dataclass(frozen=True)
class Chunk:
    text: str
    words: int
    length: str
    source: str


@dataclass(frozen=True)
class CorpusReadiness:
    """Deterministic preflight result shown before a training job can start.

    The hosted product uses a stricter minimum than the local CLI because it is
    charging for a managed model. Keeping the thresholds as arguments lets us
    calibrate them from quality data without changing the extraction rules.
    """

    status: str
    documents: int
    usable_documents: int
    raw_words: int
    usable_words: int
    chunks: int
    duplicate_chunks: int
    duplicate_words: int
    minimum_words: int
    recommended_words: int
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status != "blocked"


class CorpusTooSmall(Exception):
    pass


def read_path(path: str | Path) -> list[tuple[str, str]]:
    """(name, prose) for every readable document under a file or folder."""
    root = Path(path).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"no such path: {root}")

    files = (
        [root]
        if root.is_file()
        else sorted(p for p in root.rglob("*") if p.suffix.lower() in TEXT_SUFFIXES)
    )
    if not files:
        raise FileNotFoundError(
            f"no {'/'.join(sorted(TEXT_SUFFIXES))} files under {root}"
        )

    documents = []
    for path_ in files:
        prose = markdown.prose_only(path_.read_text(encoding="utf-8", errors="ignore"))
        if prose:
            documents.append((str(path_.relative_to(root) if root.is_dir() else path_.name), prose))
    return documents


def to_chunks(documents: list[tuple[str, str]], target_words: int = TARGET_WORDS) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[str] = set()
    for name, prose in documents:
        for text in _split_document(prose, target_words):
            words = len(text.split())
            fingerprint = _chunk_fingerprint(text)
            if words >= MIN_CHUNK_WORDS and fingerprint not in seen:
                chunks.append(Chunk(text=text, words=words, length=length_bucket(words), source=name))
                seen.add(fingerprint)
    return chunks


def inspect(
    documents: list[tuple[str, str]],
    *,
    minimum_words: int = MIN_CORPUS_WORDS,
    recommended_words: int = WEAK_CORPUS_WORDS,
) -> CorpusReadiness:
    """Return a complete readiness report without starting or charging training."""
    if minimum_words < 1 or recommended_words < minimum_words:
        raise ValueError("recommended_words must be greater than or equal to minimum_words")

    chunks, duplicate_chunks, duplicate_words = _chunks_with_duplicate_counts(documents)
    usable_words = sum(chunk.words for chunk in chunks)
    usable_sources = {chunk.source for chunk in chunks}
    raw_words = sum(len(prose.split()) for _name, prose in documents)
    reasons: list[str] = []
    warnings: list[str] = []

    if not documents:
        reasons.append("No readable documents were found.")
    if usable_words < minimum_words:
        reasons.append(
            f"Only {usable_words} usable words were found; at least {minimum_words} are required."
        )
    elif usable_words < recommended_words:
        warnings.append(
            f"{usable_words} usable words passed, but {recommended_words}+ usually produces a stronger voice."
        )
    if duplicate_chunks:
        warnings.append(
            f"Removed {duplicate_chunks} duplicate passage(s) totaling {duplicate_words} words."
        )
    ignored_documents = len(documents) - len(usable_sources)
    if ignored_documents:
        warnings.append(
            f"Ignored {ignored_documents} document(s) without a usable prose passage of "
            f"{MIN_CHUNK_WORDS}+ words."
        )

    status = "blocked" if reasons else "warning" if warnings else "ready"
    return CorpusReadiness(
        status=status,
        documents=len(documents),
        usable_documents=len(usable_sources),
        raw_words=raw_words,
        usable_words=usable_words,
        chunks=len(chunks),
        duplicate_chunks=duplicate_chunks,
        duplicate_words=duplicate_words,
        minimum_words=minimum_words,
        recommended_words=recommended_words,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def inspect_hosted(documents: list[tuple[str, str]]) -> CorpusReadiness:
    """Paid-product preflight: do not offer checkout for a marginal corpus."""
    return inspect(
        documents,
        minimum_words=HOSTED_MIN_CORPUS_WORDS,
        recommended_words=HOSTED_RECOMMENDED_CORPUS_WORDS,
    )


def _chunk_fingerprint(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return sha256(normalized.encode("utf-8")).hexdigest()


def _chunks_with_duplicate_counts(
    documents: list[tuple[str, str]], target_words: int = TARGET_WORDS
) -> tuple[list[Chunk], int, int]:
    chunks: list[Chunk] = []
    seen: set[str] = set()
    duplicate_chunks = 0
    duplicate_words = 0
    for name, prose in documents:
        for text in _split_document(prose, target_words):
            words = len(text.split())
            if words < MIN_CHUNK_WORDS:
                continue
            fingerprint = _chunk_fingerprint(text)
            if fingerprint in seen:
                duplicate_chunks += 1
                duplicate_words += words
                continue
            seen.add(fingerprint)
            chunks.append(Chunk(text=text, words=words, length=length_bucket(words), source=name))
    return chunks, duplicate_chunks, duplicate_words


def _is_prose_paragraph(paragraph: str) -> bool:
    """Outline fragments are not a voice.

    Half of what people keep in a notes app is bulleted thinking-out-loud. Train
    on it and you get a model that writes in bullets, so the corpus takes only
    paragraphs that are mostly sentences.
    """
    lines = [line for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return False
    # A headline or a stray fragment has no sentence in it. Real prose does.
    if not SENTENCE_END.search(paragraph):
        return False
    bullets = sum(bool(LIST_LINE.match(line)) for line in lines)
    return bullets / len(lines) <= MAX_LIST_SHARE


def _split_document(prose: str, target_words: int) -> list[str]:
    paragraphs = [p.strip() for p in prose.split("\n\n") if _is_prose_paragraph(p.strip())]
    if not paragraphs:
        return []
    if sum(len(p.split()) for p in paragraphs) <= SHORT_MAX_WORDS:
        return ["\n\n".join(paragraphs)]

    out: list[str] = []
    buf: list[str] = []
    buf_words = 0
    for para in paragraphs:
        para_words = len(para.split())
        if buf and buf_words + para_words > target_words:
            out.append("\n\n".join(buf))
            buf, buf_words = [], 0
        buf.append(para)
        buf_words += para_words
    if buf:
        out.append("\n\n".join(buf))
    return out


def check_size(chunks: list[Chunk], documents: list[tuple[str, str]] | None = None) -> str | None:
    """Raise if the corpus cannot work; return a warning string if it is thin.

    Below ~300 words there is nothing to learn a voice from, and training anyway
    would burn the user's money to produce a model that sounds like nobody.

    When it refuses, it says what it *did* find. "0 words of usable prose" is
    baffling to someone looking at a file full of words; "read 3 files, found 40
    words of prose, none of it in a passage long enough to use" is actionable.
    """
    total = sum(c.words for c in chunks)
    if total < MIN_CORPUS_WORDS:
        raise CorpusTooSmall(_too_small_message(total, chunks, documents))
    if total < WEAK_CORPUS_WORDS:
        return (
            f"{total} words is thin — the voice will be weak. "
            f"{WEAK_CORPUS_WORDS}+ is where it starts to sound like you."
        )
    return None


def _too_small_message(total: int, chunks: list[Chunk], documents: list[tuple[str, str]] | None) -> str:
    lines = [f"{total} words of usable prose — need at least {MIN_CORPUS_WORDS}."]

    if documents is not None:
        found = sum(len(prose.split()) for _name, prose in documents)
        lines.append(f"Read {len(documents)} file(s) and found {found} words of prose.")
        if found >= MIN_CORPUS_WORDS and not chunks:
            lines.append(
                f"None of it sat in a passage of {MIN_CHUNK_WORDS}+ words. Bulleted outlines, "
                f"headings, code and tables are skipped — only paragraphs count."
            )
    lines.append("Point it at more of your writing, or at a folder with more in it.")
    return " ".join(lines)
