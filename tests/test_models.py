import pytest

from voiceprint import models


def test_presets_resolve_to_hugging_face_ids():
    assert models.resolve("qwen14b") == "Qwen/Qwen2.5-14B"
    assert models.resolve("qwen7b") == "Qwen/Qwen2.5-7B"
    assert len(models.MODEL_PRESETS) == 2  # only bases that have been measured


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

