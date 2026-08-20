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


def test_edit_span_preserves_surrounding_text_and_revoices_replacement(monkeypatch):
    monkeypatch.setattr(engine, "revoice", lambda text, **_kwargs: f"VOICE[{text}]")

    source = "Keep this sentence. Replace these words. Keep this too."
    start = source.index("Replace")
    end = source.index(" Keep this too")
    edited = engine.edit_span(source, start, end, "Corrected private draft")

    assert edited == "Keep this sentence. VOICE[Corrected private draft] Keep this too."


def test_edit_span_rejects_invalid_offsets(monkeypatch):
    monkeypatch.setattr(engine, "revoice", lambda text, **_kwargs: text)

    for start, end in [(-1, 2), (2, 2), (3, 2), (0, 99), (True, 2)]:
        try:
            engine.edit_span("text", start, end, "replacement")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid offsets must be rejected")
