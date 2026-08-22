"""Turning chunks of someone's writing into training pairs.

Three pairs come out of every chunk, and they are what make the four user-facing
modes work off one adapter:

  write     notes -> body            (a fresh section from a brief)
  continue  body prefix -> rest      (finish what I started; also section-fill)
  rewrite   AI-sounding draft -> body (say this in my voice)

The rewrite pair is synthesized: an instruct model rewrites the author's own
paragraph into generic AI prose, and the adapter learns the reverse direction.
Nobody has to supply "before" examples, and the "after" is genuinely theirs.

Everything here is a pure function so it can be tested without a GPU. The model
calls that fill in `notes` and `degraded` happen in modal_app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from voiceprint.corpus import Chunk
from voiceprint.scaffold import Prompt, build_rewrite_prompt, build_write_prompt

NOTES_INSTRUCTION = """Read the passage. Write 3 to 6 terse bullet notes that a writer could use to \
reconstruct it from scratch: the claims it makes, the specifics it names, the order it moves in. \
Notes, not a summary — no full sentences, no commentary on the writing.

Output only the bullets, one per line, each starting with "- ".

Passage:
{body}"""

DEGRADE_INSTRUCTION = """Rewrite the passage the way a generic AI assistant would write it: correct, \
even-paced, lightly hedged, tidy transitions between every sentence, and a summarizing closer. Keep \
the same facts and roughly the same length. Do not improve it — make it bland.

Output only the rewrite.

Passage:
{body}"""

CONTINUATION_SPLIT = 0.4
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Pair:
    """One training example: what the model is shown, and the real human words
    it should produce. `prompt` is a `Prompt`, not a string — the string only
    exists once the base model's tokenizer renders it, GPU-side."""

    prompt: Prompt
    completion: str
    kind: str


def notes_request(body: str) -> str:
    return NOTES_INSTRUCTION.format(body=body)


def degrade_request(body: str) -> str:
    return DEGRADE_INSTRUCTION.format(body=body)


def parse_notes(raw: str) -> list[str]:
    """Bullets out of the instruct model's reply, tolerant of its bullet style.

    Returns [] when nothing bullet-shaped came back; the caller drops that chunk's
    write pair rather than training on a malformed brief.
    """
    notes = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        stripped = re.sub(r"^[-*•]\s*|^\d+[.)]\s*", "", line)
        if stripped != line and stripped:
            notes.append(stripped)
    return notes


def continuation_split(text: str) -> tuple[str, str]:
    """Split a body at the sentence boundary nearest 40% of the way in."""
    sentences = _SENTENCE_END.split(text.strip())
    if len(sentences) < 2:
        return "", text.strip()

    total = len(text.split())
    target = total * CONTINUATION_SPLIT
    prefix: list[str] = []
    count = 0
    for sentence in sentences[:-1]:
        prefix.append(sentence)
        count += len(sentence.split())
        if count >= target:
            break
    head = " ".join(prefix)
    tail = text.strip()[len(head) :].lstrip()
    return head, tail


def pairs_for_chunk(chunk: Chunk, notes: list[str], degraded: str) -> list[Pair]:
    body = chunk.text.strip()
    pairs: list[Pair] = []

    if notes:
        pairs.append(
            Pair(
                prompt=build_write_prompt(notes, chunk.length),
                completion=body,
                kind="write",
            )
        )

    head, tail = continuation_split(body)
    if head and tail:
        pairs.append(
            Pair(
                prompt=build_write_prompt(None, chunk.length, preceding_text=head + " "),
                completion=tail,
                kind="continue",
            )
        )

    if degraded.strip():
        pairs.append(
            Pair(
                prompt=build_rewrite_prompt(degraded),
                completion=body,
                kind="rewrite",
            )
        )

    return pairs
