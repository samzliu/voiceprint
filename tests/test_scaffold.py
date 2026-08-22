"""The invariant the whole project rests on.

If the prompt a pair was trained on ever stops matching the prompt generation
sends, the adapter is being asked at inference for something it never saw, and
the output degrades into ordinary AI prose without anything visibly breaking.
"""

import pytest

from voiceprint.corpus import Chunk
from voiceprint.prep import pairs_for_chunk
from voiceprint.scaffold import (
    MAX_TOKENS,
    SAMPLERS,
    SHORT_MAX_WORDS,
    Prompt,
    build_rewrite_prompt,
    build_write_prompt,
    length_bucket,
    render,
    stop_for,
    trim_to_sentence,
)

BODY = (
    "The wedge is trust, not features. Every tool in this category ships the same "
    "six things. What none of them do is tell you when they are wrong, which is the "
    "only thing an operator actually needs."
)


class FakeTokenizer:
    """Enough of a chat template to test the seams, without downloading a model.

    Shaped like Qwen's, which is the template the technique was measured on.
    """

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        rendered = "".join(
            f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages
        )
        if add_generation_prompt:
            rendered += "<|im_start|>assistant\n"
        return rendered


def chunk(text=BODY, length="medium"):
    return Chunk(text=text, words=len(text.split()), length=length, source="t.md")


def test_training_prompt_matches_generation_prompt():
    notes = ["the wedge is trust", "everyone ships the same six features"]
    pairs = {p.kind: p for p in pairs_for_chunk(chunk(), notes, "bland version")}

    assert pairs["write"].prompt == build_write_prompt(notes, "medium")
    assert pairs["rewrite"].prompt == build_rewrite_prompt("bland version")

    # A continuation is the same prompt with the assistant turn partly written.
    head = pairs["continue"].prompt.prefill
    assert pairs["continue"].prompt == build_write_prompt(None, "medium", preceding_text=head)


def test_rendered_training_prefix_matches_rendered_generation_prefix():
    """The identity that actually matters is over rendered *text*, not objects —
    that is what the tokenizer sees on both sides."""
    tokenizer = FakeTokenizer()
    notes = ["the wedge is trust"]
    pairs = {p.kind: p for p in pairs_for_chunk(chunk(), notes, "bland version")}

    for kind, generated in (
        ("write", build_write_prompt(notes, "medium")),
        ("rewrite", build_rewrite_prompt("bland version")),
    ):
        assert render(tokenizer, pairs[kind].prompt) == render(tokenizer, generated)


def test_the_prompt_is_a_chat_template():
    """The inverse of what this project used to assert.

    The document arm deliberately kept the chat template out of the prompt,
    because a *pretrained* base model prompted as a document reads human and the
    same model prompted as a chat turn does not. The instruct arm inverts that:
    the base has been tuned to expect this template, so training and generating
    through it is what matches the format. Either arm works. Mixing them is the
    only thing that reliably fails, which is why the format is recorded per voice.
    """
    rendered = render(FakeTokenizer(), build_write_prompt(["a"], "medium"))
    assert "<|im_start|>user" in rendered
    assert rendered.endswith("<|im_start|>assistant\n")


def test_a_continuation_hands_the_model_its_own_half_written_answer():
    rendered = render(
        FakeTokenizer(), build_write_prompt(None, "medium", preceding_text="I started this ")
    )
    assert rendered.endswith("<|im_start|>assistant\nI started this ")


def test_write_prompt_shape():
    prompt = build_write_prompt(["one", "two"], "short")
    assert prompt.prefill == ""
    assert prompt.messages == [
        {
            "role": "user",
            "content": "Write a short passage in your own voice.\n\nNotes:\n- one\n- two",
        }
    ]


def test_prompt_without_notes_omits_the_notes_block():
    assert build_write_prompt(None, "long").messages[0]["content"] == (
        "Write a long passage in your own voice."
    )


def test_unknown_length_is_refused():
    with pytest.raises(ValueError):
        build_write_prompt(["a"], "epic")


def test_a_prompt_survives_the_trip_to_the_gpu():
    """`Prompt` crosses a Modal boundary as plain data and is rebuilt there, so a
    round-trip has to be lossless or generation silently drops the prefill."""
    original = build_write_prompt(["a note"], "medium", preceding_text="Half a sentence ")
    assert Prompt.from_dict(original.to_dict()) == original


@pytest.mark.parametrize(
    "words,expected", [(1, "short"), (120, "short"), (121, "medium"), (500, "medium"), (501, "long")]
)
def test_length_buckets(words, expected):
    assert length_bucket(words) == expected


def test_a_budget_cut_ends_at_the_last_whole_sentence():
    """A draft that stops mid-word reads as broken software, not as a draft."""
    assert trim_to_sentence("First one. Second one. Third is cut off mid") == (
        "First one. Second one."
    )
    assert trim_to_sentence('He said "go." Then the tr') == 'He said "go."'
    assert trim_to_sentence("no terminator anywhere") == "no terminator anywhere"


def test_short_is_capped_to_what_short_means():
    assert MAX_TOKENS["short"] < MAX_TOKENS["medium"]
    assert MAX_TOKENS["short"] <= SHORT_MAX_WORDS * 2
    assert "\n\n" in stop_for("short")
    assert stop_for("medium") == []


def test_every_sampler_is_fully_specified():
    """vLLM applies whichever of these it is handed, so a sampler missing a key
    quietly inherits a default from the other arm."""
    for name, sampling in SAMPLERS.items():
        assert set(sampling) == {"temperature", "top_p", "min_p", "repetition_penalty"}, name
        assert sampling["temperature"] > 0, name
