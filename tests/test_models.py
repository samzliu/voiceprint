import pytest

from voiceprint import models


def test_presets_resolve_to_hugging_face_ids():
    assert models.resolve("qwen14b") == "Qwen/Qwen2.5-14B-Instruct"
    assert models.resolve("mistral24b") == "mistralai/Mistral-Small-24B-Instruct-2501"
    assert len(models.MODEL_PRESETS) == 2  # only bases that have been measured


def test_every_preset_is_an_instruct_model():
    """The adapter is trained and served through the chat template, so a preset
    without one would be a recommendation that cannot work."""
    for preset, model in models.MODEL_PRESETS.items():
        assert not models.looks_like_base(model), preset


def test_any_hugging_face_id_passes_through():
    assert models.resolve("someone/Their-Model-7B-Instruct") == "someone/Their-Model-7B-Instruct"


def test_a_bare_word_is_not_a_model():
    with pytest.raises(ValueError):
        models.resolve("bigmodel")


@pytest.mark.parametrize(
    "model",
    [
        "Qwen/Qwen2.5-14B",
        "meta-llama/Llama-3.1-8B",
        "google/gemma-2-9b",
        "mistralai/Mistral-7B-v0.3",
    ],
)
def test_pretrained_bases_are_flagged(model):
    """Flagged, not refused. The name is only a hint — `train_voice` makes the
    real check against the tokenizer before it spends any GPU time."""
    assert models.looks_like_base(model)
    warning = models.base_model_warning(model)
    assert warning and "chat template" in warning


@pytest.mark.parametrize(
    "model",
    [
        "Qwen/Qwen2.5-14B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "google/gemma-2-9b-it",
        "mistralai/Mistral-Small-24B-Instruct-2501",
        "HuggingFaceH4/zephyr-7b-beta",
    ],
)
def test_instruct_models_pass_without_a_warning(model):
    assert not models.looks_like_base(model)
    assert models.base_model_warning(model) is None


def test_resolve_never_refuses_on_the_name_alone():
    """A keyword list cannot reliably tell a tuned model from a pretrained one,
    and refusing an instruct model it failed to recognise would be worse than
    the mistake it prevents. `resolve` only validates the *shape* of the id."""
    assert models.resolve("someone/Odd-Name-7B") == "someone/Odd-Name-7B"


def test_label_shortens_known_models_only():
    assert models.label("Qwen/Qwen2.5-14B-Instruct") == "qwen14b"
    assert models.label("someone/Their-Model-7B") == "someone/Their-Model-7B"
