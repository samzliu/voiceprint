"""What the CLI and the MCP server both call.

Every generation path lives here so the two surfaces cannot drift: an agent and a
terminal get identical prose from identical arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from voiceprint import markdown, registry, remote, scorers, selection
from voiceprint.binoculars import Reading
from voiceprint.registry import FORMAT_CHAT, Voice
from voiceprint.scaffold import (
    DEFAULT_N,
    DEFAULT_SAMPLER,
    DEFAULT_TEMPERATURE,
    MAX_TOKENS,
    SAMPLERS,
    Prompt,
    build_rewrite_prompt,
    build_write_prompt,
    stop_for,
    trim_to_sentence,
)
from voiceprint.scorers import DEFAULT_DETECTOR


@dataclass
class Draft:
    text: str
    score: float
    alternates: list[tuple[str, float]] = field(default_factory=list)
    # How the detector saw the text that is actually being returned, and what it
    # cost to get there. `soft_failed` means nothing cleared the gate and this is
    # merely the closest — the caller is expected to say so out loud.
    p_human: float = 1.0
    draws: int = 1
    gated: bool = False
    soft_failed: bool = False


class WrongFormat(Exception):
    """A voice trained in a format this build cannot serve."""


def resolve(voice_name: str | None) -> Voice:
    return registry.load(voice_name or registry.default_name())


def require_chat_format(voice: Voice) -> Voice:
    """Refuse loudly rather than generating quiet nonsense.

    A document-format adapter loaded onto the instruct engine does not error —
    it produces plausible prose that has lost the voice and fails detectors,
    which is the worst possible failure because it looks like it worked.
    """
    if voice.format != FORMAT_CHAT:
        raise WrongFormat(
            f"voice '{voice.name}' was trained in the old document format on a pretrained base "
            f"model, and this build serves chat-format adapters on an instruct base. Retrain it: "
            f"`voiceprint train <path-to-your-writing> --name {voice.name}`"
        )
    return voice


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


def _sampling(sampler_name: str, temperature: float | None) -> dict:
    if sampler_name not in SAMPLERS:
        raise ValueError(f"unknown sampler {sampler_name!r} — use one of {', '.join(SAMPLERS)}")
    sampling = dict(SAMPLERS[sampler_name])
    if temperature is not None:
        sampling["temperature"] = temperature
    return sampling


def _run(
    voice: Voice,
    prompt: Prompt,
    length: str,
    n: int,
    temperature: float | None,
    scorer_name: str,
    detector_name: str | None = DEFAULT_DETECTOR,
    sampler_name: str = DEFAULT_SAMPLER,
) -> Draft:
    require_chat_format(voice)
    sampling = _sampling(sampler_name, temperature)
    scorer = scorers.build(scorer_name, voice.profile)
    detector = scorers.build_detector(detector_name)

    def draw(count: int) -> list[str]:
        candidates = remote.writer().generate.remote(
            adapter_path=voice.adapter_path,
            prompt=prompt.to_dict(),
            n=count,
            sampling=sampling,
            max_tokens=MAX_TOKENS[length],
            stop=stop_for(length),
        )
        return [
            trim_to_sentence(c["text"]) if c["finish_reason"] == "length" else c["text"]
            for c in candidates
            if c["text"].strip()
        ]

    def detect(texts: list[str]) -> list[Reading]:
        return detector.read_many(texts)

    chosen = selection.best_of_n(
        draw,
        scorer.score,
        detect=detect if detector else None,
        # With the gate off, `n` is the whole budget and the old behaviour
        # applies: draw them all, rank, return the best.
        cap=n,
    )
    return Draft(
        text=chosen.text,
        score=chosen.style,
        alternates=[(c.text, c.style) for c in chosen.alternates],
        p_human=chosen.p_human,
        draws=chosen.draws,
        gated=chosen.gated,
        soft_failed=chosen.soft_failed,
    )


def write(
    notes: list[str] | None = None,
    preceding_text: str = "",
    length: str = "medium",
    voice_name: str | None = None,
    n: int = DEFAULT_N,
    temperature: float | None = None,
    scorer_name: str = "stylometry",
    detector_name: str | None = DEFAULT_DETECTOR,
) -> Draft:
    """Fresh section, continuation, or next-section — all one call.

    Notes carry the facts. Anything not in them the model will invent, which is
    inherent to the sampling that makes the prose read human.
    """
    if not notes and not preceding_text.strip():
        raise ValueError("give it something to go on: notes, preceding text, or both")

    voice = resolve(voice_name)
    prompt = build_write_prompt(notes, length, preceding_text=preceding_text)
    return _run(voice, prompt, length, n, temperature, scorer_name, detector_name)


def rewrite(
    text: str,
    voice_name: str | None = None,
    n: int = 4,
    temperature: float | None = None,
    scorer_name: str = "stylometry",
    detector_name: str | None = DEFAULT_DETECTOR,
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
        draft = _run(
            voice,
            build_rewrite_prompt(body),
            length,
            n,
            temperature,
            scorer_name,
            detector_name,
        )
        out.append(f"{leading}{draft.text}{trailing}")
    return "".join(out)


def revoice(
    text: str,
    voice_name: str | None = None,
    n: int = 4,
    temperature: float | None = None,
    scorer_name: str = "stylometry",
    detector_name: str | None = DEFAULT_DETECTOR,
) -> str:
    """Make Voiceprint the final writer of an existing draft.

    The input may have been planned or mechanically corrected by another model,
    but only this adapter-authored result is suitable for user-visible output.
    """
    if not text.strip():
        raise ValueError("nothing to revoice")
    return rewrite(text, voice_name, n, temperature, scorer_name, detector_name)


def edit_span(
    text: str,
    start: int,
    end: int,
    replacement_draft: str,
    voice_name: str | None = None,
    n: int = 4,
    temperature: float | None = None,
    scorer_name: str = "stylometry",
    detector_name: str | None = DEFAULT_DETECTOR,
) -> str:
    """Replace one exact span, with Voiceprint writing the replacement's final words.

    `replacement_draft` is private intermediate material prepared by a human or
    planning model. Text outside the selected span is preserved byte-for-byte.

    This is the supported way to change one sentence, and the reason hand-editing
    is not: a human or an AI polish pass over finished prose re-triggers the
    detectors on the whole passage (one run went from 0.9997 to 0.00). To change
    something, change the input and let the adapter write the final words again.
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
        detector_name=detector_name,
    )
    return f"{text[:start]}{replacement}{text[end:]}"
