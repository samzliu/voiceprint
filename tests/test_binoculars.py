"""The detector's thresholding and its short-text guard.

The two forward passes need a GPU and are not tested here. Everything that turns
a raw score into a decision is pure, and that is the part that can be wrong in a
way nobody notices.
"""

from voiceprint import binoculars


def test_the_probability_crosses_a_half_exactly_at_the_threshold():
    """`selection` gates on `p_human > 0.5`, so this mapping is what makes the
    published operating point mean what it says."""
    assert binoculars.p_human(binoculars.DEFAULT_THRESHOLD) == 0.5
    assert binoculars.p_human(binoculars.DEFAULT_THRESHOLD + 0.05) > 0.5
    assert binoculars.p_human(binoculars.DEFAULT_THRESHOLD - 0.05) < 0.5


def test_the_probability_is_monotone_in_the_score():
    scores = [0.5, 0.7, 0.85, 0.9, 1.1]
    probabilities = [binoculars.p_human(s) for s in scores]
    assert probabilities == sorted(probabilities)


def test_the_default_operating_point_is_the_cautious_one():
    """A false 'machine-written' costs one redraw. A false 'this is fine' ships
    the thing the user is paying us to avoid."""
    assert binoculars.DEFAULT_THRESHOLD == binoculars.THRESHOLD_LOW_FPR
    assert binoculars.THRESHOLD_LOW_FPR < binoculars.THRESHOLD_ACCURACY


def test_machine_scores_low_and_human_scores_high():
    """The direction of the ratio, which is easy to invert by accident and
    produces a detector that is confidently backwards."""
    assert binoculars.reading(0.5, tokens=100).p_human < 0.5
    assert binoculars.reading(1.1, tokens=100).p_human > 0.5


def test_short_text_is_marked_unreliable_and_passes():
    short = binoculars.reading(0.1, tokens=binoculars.MIN_TOKENS - 1)
    assert not short.reliable
    assert short.passed  # cannot judge it, so does not reject it

    long = binoculars.reading(0.1, tokens=binoculars.MIN_TOKENS)
    assert long.reliable
    assert not long.passed


def test_a_reading_survives_the_trip_back_from_the_gpu():
    original = binoculars.reading(0.87, tokens=120)
    assert binoculars.Reading.from_dict(original.to_dict()) == original
