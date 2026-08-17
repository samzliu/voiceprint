"""The document format, and the sampler settings that go with it.

This module is the whole trick, so it is the single source of truth for both
training and generation. Two rules produced every result the project rests on:

1. The model always sees a *plain document*, never a chat template. The same base
   model given the same brief as a chat instruction is caught by AI detectors
   100% of the time; formatted as a document it reads human.
2. min-p sampling at high temperature. Top-p is the worst option here, and low
   temperature collapses the variance that makes prose read like a person.

`tests/test_scaffold.py` asserts that the prompt a training pair is built from is
byte-identical to the prompt generation sends. If those ever drift, the adapter
is being asked at inference for something it was never trained on, and the
output quietly degrades into ordinary AI prose.
"""

from __future__ import annotations

import re

SHORT_MAX_WORDS = 120
MEDIUM_MAX_WORDS = 500
LENGTHS = ("short", "medium", "long")

# Sampling. The temperature is the polish-vs-variance dial: lower is cleaner and
# reads more like a machine, higher reads human and glitches more often.
DEFAULT_TEMPERATURE = 1.5
DEFAULT_MIN_P = 0.05
DEFAULT_N = 8
# Budgets follow the length definitions above, so "short" cannot ramble past what
# short means. Whatever the budget cuts off is trimmed back to the last complete
# sentence; see `trim_to_sentence`.
MAX_TOKENS = {"short": 200, "medium": 900, "long": 2000}

# The model is trained to emit EOS at the end of a body. These are belt-and-braces
# for the case where it instead starts a fresh document.
STOP_SEQUENCES = ["\nNotes:", "\nDraft:", "\nLength:"]


def stop_for(length: str) -> list[str]:
    """A short piece is one block, by definition.

    Without this the model keeps going after a two-line reply and staples on
    another unrelated one, because a blank line looks to it like the middle of a
    document rather than the end of one.
    """
    if length == "short":
        return STOP_SEQUENCES + ["\n\n"]
    return STOP_SEQUENCES


def length_bucket(word_count: int) -> str:
    """Which length the model should be told to write. Buckets are assigned from
    real word counts at prep time so the control is trained, not just truncated."""
    if word_count <= SHORT_MAX_WORDS:
        return "short"
    if word_count <= MEDIUM_MAX_WORDS:
        return "medium"
    return "long"


def build_write_prompt(
    notes: list[str] | None,
    length: str,
    preceding_text: str = "",
) -> str:
    """The one generation prompt.

    Fresh section:  notes, no preceding_text.
    Continuation:   preceding_text, notes optional.
    Next section:   both — the tail of the previous section conditions this one.

    A body prefix is just a partially-filled `Write-up:`, which is why all three
    modes are one code path.
    """
    if length not in LENGTHS:
        raise ValueError(f"length must be one of {LENGTHS}, got {length!r}")

    head = ""
    if notes:
        bullets = "\n".join(f"- {n.strip()}" for n in notes if n.strip())
        head = f"Notes:\n{bullets}\n"
    return f"{head}Length: {length}\n\nWrite-up:\n{preceding_text}"


def build_rewrite_prompt(draft: str) -> str:
    """Rewrite is the one genuinely different task: the source text's content has
    to survive, so the model is shown it rather than notes about it."""
    return f"Draft:\n{draft.strip()}\n\nRewrite:\n"


_LAST_SENTENCE = re.compile(r"^.*[.!?][\"'”’)\]]*", re.DOTALL)


def trim_to_sentence(text: str) -> str:
    """End at the last complete sentence.

    Only used when the token budget cut a generation off mid-sentence. A draft
    that stops in the middle of a word reads as broken software rather than as a
    draft, and the half-sentence carries no information the user wanted.
    """
    match = _LAST_SENTENCE.match(text.strip())
    if not match:
        return text.strip()
    return match.group(0).strip()
