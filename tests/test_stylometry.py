import json

from voiceprint import stylometry
from voiceprint.stylometry import Profile

AUTHOR = [
    "The wedge is trust, not features. Everyone ships the same six things and none of them "
    "tell you when they are wrong.",
    "I spent a week on it and the week was the point. You cannot shortcut the part where you "
    "find out what you actually think.",
    "Most of this is bookkeeping. The interesting decisions are three lines long and you make "
    "them in the first hour.",
]

SLOP = (
    "In today's fast-paced world, it's important to note that leveraging synergies is not just "
    "a strategy, but a necessity. Let's dive into the key considerations. Ultimately, the "
    "landscape continues to evolve in exciting ways."
)


def test_profile_survives_a_json_round_trip():
    """The profile lives in the local registry as JSON, which is what lets ranking
    happen on the user's machine after the corpus is gone."""
    profile = stylometry.fit(AUTHOR)
    restored = Profile.from_dict(json.loads(json.dumps(profile.to_dict())))
    assert stylometry.score(restored, AUTHOR[0]) == stylometry.score(profile, AUTHOR[0])


def test_the_authors_own_writing_outscores_ai_slop():
    profile = stylometry.fit(AUTHOR)
    assert stylometry.score(profile, AUTHOR[0]) > stylometry.score(profile, SLOP)


def test_empty_text_scores_zero():
    assert stylometry.score(stylometry.fit(AUTHOR), "   ") == 0.0


def test_novelty_catches_recitation():
    """The memorization guard: a model that hands back its training text is
    supplying nothing, however well it scores on style."""
    recited = AUTHOR[0]
    assert stylometry.novelty(recited, AUTHOR) < 0.1


def test_novelty_is_high_for_genuinely_new_prose():
    fresh = (
        "Nobody asks what the operator does at four in the afternoon, when the queue is empty "
        "and the only thing left is deciding which of yesterday's calls to reopen."
    )
    assert stylometry.novelty(fresh, AUTHOR) > 0.95


def test_slop_markers_penalize_the_usual_tells():
    assert stylometry.slop_penalty(SLOP) > stylometry.slop_penalty(AUTHOR[0])
