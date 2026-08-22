"""The chat format, and the sampler settings that go with it.

This module is the whole trick, so it is the single source of truth for both
training and generation. One rule produces every result the project rests on:

    Train on human text in the format you generate in.

We generate through the base model's chat template, so we train through the chat
template too: the user turn is an instruction, the assistant turn is a real
paragraph the author actually wrote, and loss falls on the assistant span only.
Either half alone fails. A vanilla instruct model asked for a paragraph is caught
by detectors every time, because the RLHF assistant distribution *is* the
fingerprint. A model fine-tuned on plain documents but prompted with the chat
template also fails, because it is being asked at inference for something it was
never trained on. Matching them is the entire technique.

`tests/test_scaffold.py` asserts that the prompt a training pair is built from is
byte-identical to the prompt generation sends. If those ever drift, the adapter
degrades into ordinary AI prose without anything visibly breaking.

Rendering to a string needs the base model's tokenizer, which only exists on the
GPU side. So this module builds `Prompt` objects — plain data, testable without
a GPU — and `render()` turns one into the exact text the model sees. Training and
generation both call `render()`, which is what keeps them honest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SHORT_MAX_WORDS = 120
MEDIUM_MAX_WORDS = 500
LENGTHS = ("short", "medium", "long")

# Sampling. The standard sampler is the one the research validated on the chat
# arm: it produced both the best prose and a 100% detector pass rate, which is
# not the tradeoff the document arm had. `diverse` is kept for when a voice
# keeps returning near-identical drafts and best-of-N stops buying anything.
SAMPLERS = {
    "standard": {"temperature": 1.0, "top_p": 0.95, "min_p": 0.0, "repetition_penalty": 1.0},
    "diverse": {"temperature": 1.5, "top_p": 1.0, "min_p": 0.05, "repetition_penalty": 1.1},
}
DEFAULT_SAMPLER = "standard"
DEFAULT_TEMPERATURE = SAMPLERS[DEFAULT_SAMPLER]["temperature"]

# The candidate budget. With the detector gating draws this is a *cap* that is
# rarely reached, not a batch size — see `voiceprint/selection.py`. With the
# detector off it is drawn in full, every time.
DEFAULT_N = 6

# Budgets follow the length definitions above, so "short" cannot ramble past what
# short means. Whatever the budget cuts off is trimmed back to the last complete
# sentence; see `trim_to_sentence`.
#
# NOTE: long-form is where this technique is weakest. Training a model to emit
# long polished essays measurably *raises* detectability (one run: pass rate 1.00
# -> 0.62), because sustained polish is itself the tell. The durable shape for a
# long piece is several short passing passages stitched together, not one long
# generation. The `long` budget is kept because length control is trained rather
# than truncated, but prefer `medium` chunks and section-fill for anything real.
MAX_TOKENS = {"short": 200, "medium": 900, "long": 2000}


@dataclass(frozen=True)
class Prompt:
    """Exactly what the model is conditioned on, before any sampling.

    `messages` is the chat prefix. `prefill` is assistant text that already
    exists and that the model continues from — how "finish what I started"
    works without a second code path. At training time `prefill` is part of the
    masked prefix; at generation time it is the start of the answer. Same
    string either way, which is the point.
    """

    messages: list[dict] = field(default_factory=list)
    prefill: str = ""

    def to_dict(self) -> dict:
        return {"messages": [dict(m) for m in self.messages], "prefill": self.prefill}

    @classmethod
    def from_dict(cls, data: dict) -> "Prompt":
        return cls(messages=[dict(m) for m in data["messages"]], prefill=data.get("prefill", ""))


def render(tokenizer, prompt: Prompt) -> str:
    """A Prompt -> the literal text the model is conditioned on.

    Called by training to build the masked prefix and by generation to build the
    request. There is deliberately no second implementation anywhere: if this
    function is wrong, it is wrong identically on both sides and the adapter
    still matches itself.
    """
    text = tokenizer.apply_chat_template(
        prompt.messages, tokenize=False, add_generation_prompt=True
    )
    return text + prompt.prefill


def length_bucket(word_count: int) -> str:
    """Which length the model should be told to write. Buckets are assigned from
    real word counts at prep time so the control is trained, not just truncated."""
    if word_count <= SHORT_MAX_WORDS:
        return "short"
    if word_count <= MEDIUM_MAX_WORDS:
        return "medium"
    return "long"


def _instruction(notes: list[str] | None, length: str, continuing: bool) -> str:
    if length not in LENGTHS:
        raise ValueError(f"length must be one of {LENGTHS}, got {length!r}")

    verb = "Continue this passage" if continuing else f"Write a {length} passage"
    lines = [f"{verb} in your own voice."]
    if notes:
        bullets = "\n".join(f"- {note.strip()}" for note in notes if note.strip())
        lines.append(f"\nNotes:\n{bullets}")
    return "\n".join(lines)


def build_write_prompt(
    notes: list[str] | None,
    length: str,
    preceding_text: str = "",
) -> Prompt:
    """The one generation prompt.

    Fresh section:  notes, no preceding_text.
    Continuation:   preceding_text, notes optional.
    Next section:   both — the tail of the previous section conditions this one.

    A body prefix is just an assistant turn that is already partly written,
    which is why all three modes are one code path.
    """
    content = _instruction(notes, length, continuing=bool(preceding_text.strip()))
    return Prompt(messages=[{"role": "user", "content": content}], prefill=preceding_text)


def build_rewrite_prompt(draft: str) -> Prompt:
    """Rewrite is the one genuinely different task: the source text's content has
    to survive, so the model is shown it rather than notes about it."""
    content = (
        "Rewrite this in your own voice. Keep the facts and roughly the length.\n\n"
        f"{draft.strip()}"
    )
    return Prompt(messages=[{"role": "user", "content": content}])


def stop_for(length: str) -> list[str]:
    """A short piece is one block, by definition.

    The document arm needed a list of stop markers here to stop the base model
    from starting a fresh document after it finished one. The chat arm does not:
    the assistant turn is trained to end with the template's own end-of-turn
    token, and vLLM stops on it. Only the length guard is left.
    """
    return ["\n\n"] if length == "short" else []


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
