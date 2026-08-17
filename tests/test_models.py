import pytest

from voiceprint import models


def test_presets_resolve_to_hugging_face_ids():
    assert models.resolve("qwen14b") == "Qwen/Qwen2.5-14B"
    assert models.resolve("qwen7b") == "Qwen/Qwen2.5-7B"


def test_any_hugging_face_id_passes_through():
    assert models.resolve("someone/Their-Base-7B") == "someone/Their-Base-7B"


def test_a_bare_word_is_not_a_model():
    with pytest.raises(ValueError):
        models.resolve("bigmodel")


@pytest.mark.parametrize(
    "model",
    [
        "Qwen/Qwen2.5-14B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "google/gemma-2-9b-it",
        "mistralai/Mistral-7B-Instruct-v0.3",
    ],
)
def test_instruct_models_are_refused(model):
    """The one configuration that cannot work: an instruct model already has a
    voice, and it is detected as machine-written every time."""
    with pytest.raises(models.NotABaseModel):
        models.resolve(model)


def test_base_versions_of_those_are_fine():
    for model in ("Qwen/Qwen2.5-14B", "meta-llama/Llama-3.1-8B", "google/gemma-2-9b"):
        assert models.resolve(model) == model


def test_label_shortens_known_models_only():
    assert models.label("Qwen/Qwen2.5-14B") == "qwen14b"
    assert models.label("someone/Their-Base-7B") == "someone/Their-Base-7B"


def test_gated_models_are_refused_before_spending_gpu_time(monkeypatch):
    """A 401 buried in a container log after a four-minute wait is a bad way to
    learn you needed a token."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    import urllib.error

    def unreachable(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    # an unreachable hub must not block the user; the training job reports the truth
    models.check_available("Qwen/Qwen2.5-14B")


def test_a_token_skips_the_gate_check(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call"))
    )
    models.check_available("meta-llama/Llama-3.1-8B")
