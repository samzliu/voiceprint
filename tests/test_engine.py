from types import SimpleNamespace

from voiceprint import engine


def test_score_text_scores_the_exact_input(monkeypatch):
    seen = []

    class ExactScorer:
        def score(self, text):
            seen.append(text)
            return 0.73

    monkeypatch.setattr(engine, "resolve", lambda _name: SimpleNamespace(profile="profile"))
    monkeypatch.setattr(engine.scorers, "build", lambda name, profile: ExactScorer())

    artifact = "The exact final artifact — including its last edit."
    assert engine.score_text(artifact, voice_name="sam", scorer_name="stylometry") == 0.73
    assert seen == [artifact]


def test_score_text_rejects_empty_artifacts():
    try:
        engine.score_text("  ")
    except ValueError as error:
        assert str(error) == "nothing to score"
    else:
        raise AssertionError("empty artifacts must not receive a score")
