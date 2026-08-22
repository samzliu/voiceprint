from types import SimpleNamespace

from voiceprint import engine, registry


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


def _voice(fmt):
    return SimpleNamespace(name="sam", format=fmt, profile="profile", adapter_path="/voices/sam")


def test_a_chat_format_voice_is_served():
    assert engine.require_chat_format(_voice(registry.FORMAT_CHAT)).name == "sam"


def test_a_document_format_voice_is_refused_before_it_reaches_the_gpu():
    """The failure this prevents is the quiet one. A document-format adapter on
    the instruct engine does not error — it returns fluent prose that has lost
    the voice and fails detectors, which reads as the product being bad rather
    than as a mismatch."""
    try:
        engine.require_chat_format(_voice(registry.FORMAT_DOCUMENT))
    except engine.WrongFormat as error:
        assert "retrain" in str(error).lower()
        assert "voiceprint train" in str(error)
    else:
        raise AssertionError("a document-format voice must not be served by the instruct engine")


def test_the_detector_gate_can_be_turned_off(monkeypatch):
    """`--detector none` has to reach `best_of_n` as an actual None, not as the
    string 'none' — a truthy string would silently re-enable the gate."""
    captured = {}

    monkeypatch.setattr(engine.scorers, "build", lambda name, profile: SimpleNamespace(score=len))
    monkeypatch.setattr(
        engine.selection,
        "best_of_n",
        lambda draw, rank, detect, cap: captured.setdefault("detect", detect)
        or SimpleNamespace(text="t", style=0.0, alternates=[], p_human=1.0, draws=1, gated=False, soft_failed=False),
    )

    engine._run(_voice(registry.FORMAT_CHAT), None, "medium", 6, None, "stylometry", "none")
    assert captured["detect"] is None
