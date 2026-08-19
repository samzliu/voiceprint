import pytest

from voiceprint.modal_app import (
    parse_demo_brief,
    parse_hosted_generation,
    parse_hosted_training,
)


def test_parse_demo_brief_accepts_bullets():
    assert parse_demo_brief("- Write about agent memory\n* Make the ending practical") == [
        "Write about agent memory",
        "Make the ending practical",
    ]


@pytest.mark.parametrize("brief", [None, "short", "x" * 1_201])
def test_parse_demo_brief_rejects_bad_input(brief):
    with pytest.raises(ValueError):
        parse_demo_brief(brief)


def test_parse_demo_brief_caps_note_count():
    with pytest.raises(ValueError, match="8 notes"):
        parse_demo_brief("\n".join(f"- substantive note number {i}" for i in range(9)))


def _hosted_chunks(words=1_000):
    text = " ".join(["sentence."] * words)
    return [{"text": text, "words": 1, "length": "short", "source": "sample.md"}]


def test_hosted_training_recomputes_word_counts():
    name, chunks, model = parse_hosted_training(
        {"name": "model_abc", "chunks": _hosted_chunks(), "model": "Qwen/Qwen2.5-14B"}
    )
    assert name == "model_abc"
    assert chunks[0]["words"] == 1_000
    assert chunks[0]["length"] == "long"
    assert model == "Qwen/Qwen2.5-14B"


def test_hosted_training_blocks_too_few_real_words():
    with pytest.raises(ValueError, match="1,000 usable words"):
        parse_hosted_training({"name": "model_abc", "chunks": _hosted_chunks(999)})


def test_hosted_generation_requires_adapter_owned_path_shape():
    with pytest.raises(ValueError, match="adapter path"):
        parse_hosted_generation(
            {
                "adapter_path": "/voices/../../other",
                "provider_model": "Qwen/Qwen2.5-14B",
                "notes": ["A factual note"],
                "style_profile": {},
            }
        )


def test_hosted_generation_accepts_bounded_write_request():
    request = parse_hosted_generation(
        {
            "adapter_path": "/voices/model_abc",
            "provider_model": "Qwen/Qwen2.5-14B",
            "operation": "write",
            "length": "medium",
            "notes": ["A factual note"],
            "style_profile": {"profile": "placeholder"},
            "mode": "edited",
        }
    )
    assert request["notes"] == ["A factual note"]
    assert request["mode"] == "edited"
