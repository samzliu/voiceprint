"""Choosing which draft to hand back.

The old rule was: draw N, rank them by style, return the best. That spends the
full N every time and never asks the one question the user actually cares about,
which is whether the thing reads as machine-written.

The rule here is quality-aware best-of-N with an adaptive early stop. Draw a
small batch, ask the detector, and return as soon as something passes. Since a
single candidate from a trained adapter passes roughly 75-95% of the time, the
common case costs one batch rather than eight generations — and on a paid GPU
that early stop is the largest per-request cost lever there is.

Two details worth keeping:

  * The detector decides *whether* a draft ships; the style scorer decides
    *which* of the passing drafts ships. They answer different questions and
    ranking by either one alone gets it wrong. The spec this implements uses an
    LLM quality judge for the second question; stylometry is the local, free
    stand-in, and it is measuring closeness to the author rather than absolute
    quality.
  * If nothing passes inside the cap we return the closest thing and say so,
    rather than looping until the budget is gone. `soft_failed` is how the
    caller knows to warn.

Pure functions over injected callables, so the whole policy is testable without
a GPU or an API key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from voiceprint.binoculars import Reading

# Two at a time, not one. A single draw is the cheapest possible request but
# costs a full round-trip per retry, and drawing two gives the "more than one
# passed, keep the best-written one" branch something to actually choose
# between. Usually this is the only batch we pay for.
BATCH = 2
MAX_CANDIDATES = 6


@dataclass
class Candidate:
    text: str
    style: float = 0.0
    reading: Reading | None = None

    @property
    def p_human(self) -> float:
        return self.reading.p_human if self.reading else 1.0

    @property
    def passed(self) -> bool:
        return self.reading.passed if self.reading else True


@dataclass
class Selection:
    text: str
    style: float
    p_human: float
    alternates: list[Candidate] = field(default_factory=list)
    draws: int = 0
    soft_failed: bool = False
    gated: bool = False


def best_of_n(
    draw: Callable[[int], list[str]],
    rank: Callable[[str], float],
    detect: Callable[[list[str]], list[Reading]] | None = None,
    batch: int = BATCH,
    cap: int = MAX_CANDIDATES,
) -> Selection:
    """Draw until something passes the detector, then return the best of those.

    With `detect=None` this degrades to the plain behaviour: one draw of `cap`
    candidates ranked by style. That path is what runs when someone has turned
    the detector off, and it must stay cheap and predictable.
    """
    if not detect:
        texts = draw(cap)
        scored = _score(texts, rank)
        if not scored:
            raise RuntimeError("the model returned nothing — try again, or lower --temp")
        return _selection(scored, draws=len(scored), gated=False)

    seen: list[Candidate] = []
    while len(seen) < cap:
        wanted = min(batch, cap - len(seen))
        fresh = _score(draw(wanted), rank)
        # One detector call for the whole batch. Scoring candidates one at a
        # time doubles the round-trips for no benefit; the readings are
        # independent.
        for candidate, opinion in zip(fresh, detect([c.text for c in fresh])):
            candidate.reading = opinion
        seen.extend(fresh)

        passing = [c for c in seen if c.passed]
        if passing:
            return _selection(passing, draws=len(seen), gated=True, rest=seen)

        if not fresh:  # the model is returning nothing; retrying will not fix it
            break

    if not seen:
        raise RuntimeError("the model returned nothing — try again, or lower --temp")
    return _selection(seen, draws=len(seen), gated=True, soft_failed=True, key="p_human")


def _score(texts: list[str], rank: Callable[[str], float]) -> list[Candidate]:
    return [Candidate(text=t, style=rank(t)) for t in texts if t and t.strip()]


def _selection(
    pool: list[Candidate],
    draws: int,
    gated: bool,
    rest: list[Candidate] | None = None,
    soft_failed: bool = False,
    key: str = "style",
) -> Selection:
    """Best first. Ranked by style among drafts that passed, or by how close it
    got when none of them did — those are different questions and the sort key
    has to follow which one we are answering."""
    ordered = sorted(pool, key=lambda c: -getattr(c, key))
    best = ordered[0]
    others = [c for c in (rest or ordered) if c is not best]
    return Selection(
        text=best.text,
        style=best.style,
        p_human=best.p_human,
        alternates=sorted(others, key=lambda c: -getattr(c, key)),
        draws=draws,
        soft_failed=soft_failed,
        gated=gated,
    )
