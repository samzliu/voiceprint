"""What the CLI and the MCP server both call.

Every generation path lives here so the two surfaces cannot drift: an agent and a
terminal get identical prose from identical arguments.
"""

from __future__ import annotations

from dataclasses import dataclass

from voiceprint import markdown, registry, remote, scorers
from voiceprint.registry import Voice
from voiceprint.scaffold import (
    DEFAULT_MIN_P,
    DEFAULT_N,
    DEFAULT_TEMPERATURE,
    MAX_TOKENS,
    build_rewrite_prompt,
    build_write_prompt,
    stop_for,
    trim_to_sentence,
)


@dataclass
class Draft:
    text: str
    score: float
    alternates: list[tuple[str, float]]


def resolve(voice_name: str | None) -> Voice:
    return registry.load(voice_name or registry.default_name())


def score_text(text: str, voice_name: str | None = None, scorer_name: str = "stylometry") -> float:
    """Score the exact artifact the user is about to publish.

    Keeping this separate from generation matters: even a small edit can change
    a detector or style score, so a candidate's score must never be attached to
    a later revision.
    """
    if not text.strip():
        raise ValueError("nothing to score")
    voice = resolve(voice_name)
    return scorers.build(scorer_name, voice.profile).score(text)


def _run(voice: Voice, prompt: str, length: str, n: int, temperature: float, scorer_name: str) -> Draft:
    candidates = remote.writer(voice.model).generate.remote(
        adapter_path=voice.adapter_path,
        prompt=prompt,
        n=n,
        temperature=temperature,
        min_p=DEFAULT_MIN_P,
        max_tokens=MAX_TOKENS[length],
        stop=stop_for(length),
    )
    texts = [
        trim_to_sentence(c["text"]) if c["finish_reason"] == "length" else c["text"]
        for c in candidates
        if c["text"].strip()
    ]
    if not texts:
        raise RuntimeError("the model returned nothing — try again, or lower --temp")

    scorer = scorers.build(scorer_name, voice.profile)
    ranked = sorted(((t, scorer.score(t)) for t in texts), key=lambda pair: -pair[1])
    return Draft(text=ranked[0][0], score=ranked[0][1], alternates=ranked[1:])


def write(
    notes: list[str] | None = None,
    preceding_text: str = "",
    length: str = "medium",
    voice_name: str | None = None,
    n: int = DEFAULT_N,
    temperature: float = DEFAULT_TEMPERATURE,
    scorer_name: str = "stylometry",
) -> Draft:
    """Fresh section, continuation, or next-section — all one call.

    Notes carry the facts. Anything not in them the model will invent, which is
    inherent to the sampling that makes the prose read human.
    """
    if not notes and not preceding_text.strip():
        raise ValueError("give it something to go on: notes, preceding text, or both")

    voice = resolve(voice_name)
    prompt = build_write_prompt(notes, length, preceding_text=preceding_text)
    return _run(voice, prompt, length, n, temperature, scorer_name)


def rewrite(
    text: str,
    voice_name: str | None = None,
    n: int = 4,
    temperature: float = DEFAULT_TEMPERATURE,
    scorer_name: str = "stylometry",
) -> str:
    """Say this in my voice. Prose blocks are rewritten one at a time; code,
    headings, tables and quotes pass through untouched."""
    voice = resolve(voice_name)
    out = []
    for kind, block in markdown.segment(text):
        if kind == markdown.KEEP or not block.strip():
            out.append(block)
            continue
        leading = block[: len(block) - len(block.lstrip("\n"))]
        trailing = block[len(block.rstrip("\n")) :]
        body = block.strip()
        length = "short" if len(body.split()) <= 120 else "medium"
        draft = _run(voice, build_rewrite_prompt(body), length, n, temperature, scorer_name)
        out.append(f"{leading}{draft.text}{trailing}")
    return "".join(out)


def revoice(
    text: str,
    voice_name: str | None = None,
    n: int = 4,
    temperature: float = DEFAULT_TEMPERATURE,
    scorer_name: str = "stylometry",
) -> str:
    """Make Voiceprint the final writer of an existing draft.

    The input may have been planned or mechanically corrected by another model,
    but only this adapter-authored result is suitable for user-visible output.
    """
    if not text.strip():
        raise ValueError("nothing to revoice")
    return rewrite(text, voice_name, n, temperature, scorer_name)


def edit_span(
    text: str,
    start: int,
    end: int,
    replacement_draft: str,
    voice_name: str | None = None,
    n: int = 4,
    temperature: float = DEFAULT_TEMPERATURE,
    scorer_name: str = "stylometry",
) -> str:
    """Replace one exact span, with Voiceprint writing the replacement's final words.

    `replacement_draft` is private intermediate material prepared by a human or
    planning model. Text outside the selected span is preserved byte-for-byte.
    """
    if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
        raise ValueError("span offsets must be integers")
    if start < 0 or end <= start or end > len(text):
        raise ValueError("invalid edit span")
    if not replacement_draft.strip():
        raise ValueError("replacement draft is empty")
    replacement = revoice(
        replacement_draft,
        voice_name=voice_name,
        n=n,
        temperature=temperature,
        scorer_name=scorer_name,
    )
    return f"{text[:start]}{replacement}{text[end:]}"
