"""The selection policy: what ships, and what it costs to find it.

All of it is exercised through injected callables, so these tests pin the
*policy* — how many draws, which candidate wins, what happens when nothing
passes — without a GPU or a detector anywhere near them.
"""

import pytest

from voiceprint import binoculars
from voiceprint.selection import BATCH, MAX_CANDIDATES, best_of_n

PASSING = binoculars.THRESHOLD_LOW_FPR + 0.1
FAILING = binoculars.THRESHOLD_LOW_FPR - 0.1


class Draws:
    """A stand-in generator that records what was asked of it."""

    def __init__(self, texts=None):
        self.requested = []
        self.texts = texts

    def __call__(self, count):
        self.requested.append(count)
        if self.texts is not None:
            return self.texts[:count]
        n = len(self.requested)
        return [f"candidate {n}-{i} with enough words to look like prose" for i in range(count)]

    @property
    def total(self):
        return sum(self.requested)


def reading(score, tokens=100):
    return binoculars.reading(score, tokens)


def always(score):
    return lambda texts: [reading(score) for _ in texts]


def test_a_passing_first_batch_costs_one_batch():
    """The whole point of the adaptive stop. A trained adapter passes most of the
    time, so the common case must not pay for the full cap."""
    draw = Draws()
    chosen = best_of_n(draw, len, detect=always(PASSING))

    assert draw.requested == [BATCH]
    assert chosen.draws == BATCH
    assert chosen.gated
    assert not chosen.soft_failed


def test_it_keeps_drawing_while_candidates_fail():
    draw = Draws()
    chosen = best_of_n(draw, len, detect=always(FAILING))

    assert draw.total == MAX_CANDIDATES
    assert chosen.soft_failed


def test_nothing_passing_returns_the_closest_rather_than_nothing():
    """A soft fail still has to hand back prose — the caller warns, the user
    decides. Returning an error here would throw away six paid generations."""
    scores = iter([0.10, 0.20, 0.30, 0.85, 0.40, 0.50])
    chosen = best_of_n(
        Draws(),
        len,
        detect=lambda texts: [reading(next(scores)) for _ in texts],
    )
    assert chosen.soft_failed
    # 0.85 is still under the threshold, so it did not pass — but it is closest.
    assert chosen.p_human == max(binoculars.p_human(s) for s in (0.10, 0.20, 0.30, 0.85, 0.40, 0.50))


def test_among_passing_candidates_the_best_written_one_wins():
    """The detector says which drafts are allowed to ship; the style scorer picks
    between them. Ranking by p_human instead would optimise for the detector."""
    draw = Draws(texts=["short one", "the considerably longer candidate"])
    chosen = best_of_n(draw, rank=len, detect=always(PASSING))
    assert chosen.text == "the considerably longer candidate"


def test_a_draft_too_short_to_judge_is_not_thrown_away():
    """Under about 40 tokens every detector is guessing. Gating on that noise
    would reject good short replies at random."""
    chosen = best_of_n(Draws(), len, detect=lambda texts: [reading(FAILING, tokens=10) for _ in texts])
    assert not chosen.soft_failed
    assert chosen.draws == BATCH


def test_with_no_detector_it_draws_the_whole_budget_once():
    draw = Draws()
    chosen = best_of_n(draw, len, detect=None, cap=8)

    assert draw.requested == [8]
    assert not chosen.gated
    assert not chosen.soft_failed
    assert len(chosen.alternates) == 7


def test_blank_candidates_are_dropped_before_they_are_scored():
    draw = Draws(texts=["", "   ", "a real draft"])
    chosen = best_of_n(draw, len, detect=None, cap=3)
    assert chosen.text == "a real draft"
    assert chosen.alternates == []


def test_a_model_returning_nothing_at_all_stops_instead_of_looping():
    with pytest.raises(RuntimeError):
        best_of_n(lambda count: [], len, detect=always(PASSING))


def test_the_returned_reading_belongs_to_the_returned_text():
    """A score attached to a different candidate is worse than no score: the
    caller reports it to the user as a fact about the text they are holding."""
    scores = {"short one": 0.95, "the considerably longer candidate": 0.99}
    draw = Draws(texts=list(scores))
    chosen = best_of_n(
        draw,
        rank=len,
        detect=lambda texts: [reading(scores[t]) for t in texts],
    )
    assert chosen.text == "the considerably longer candidate"
    assert chosen.p_human == binoculars.p_human(0.99)
