"""The invariant the whole project rests on.

If the prompt a pair was trained on ever stops matching the prompt generation
sends, the adapter is being asked at inference for something it never saw, and
the output degrades into ordinary AI prose without anything visibly breaking.
"""

import pytest

from voiceprint.corpus import Chunk
from voiceprint.prep import pairs_for_chunk
from voiceprint.scaffold import build_rewrite_prompt, build_write_prompt, length_bucket

BODY = (
    "The wedge is trust, not features. Every tool in this category ships the same "
    "six things. What none of them do is tell you when they are wrong, which is the "
    "only thing an operator actually needs."
)


def chunk(text=BODY, length="medium"):
    return Chunk(text=text, words=len(text.split()), length=length, source="t.md")


def test_training_prompt_matches_generation_prompt():
    notes = ["the wedge is trust", "everyone ships the same six features"]
    pairs = {p.kind: p for p in pairs_for_chunk(chunk(), notes, "bland version")}

    assert pairs["write"].prompt == build_write_prompt(notes, "medium")
    assert pairs["rewrite"].prompt == build_rewrite_prompt("bland version")

    # A continuation is the same prompt with the body partly filled in.
    head = pairs["continue"].prompt.split("Write-up:\n", 1)[1]
    assert pairs["continue"].prompt == build_write_prompt(None, "medium", preceding_text=head)


def test_write_prompt_shape():
    prompt = build_write_prompt(["one", "two"], "short")
    assert prompt == "Notes:\n- one\n- two\nLength: short\n\nWrite-up:\n"


def test_prompt_without_notes_omits_the_notes_block():
    assert build_write_prompt(None, "long") == "Length: long\n\nWrite-up:\n"


def test_prompt_is_never_a_chat_template():
    prompt = build_write_prompt(["a"], "medium", preceding_text="Half a sentence")
    for marker in ("<|im_start|>", "<|im_end|>", "system", "assistant", "User:"):
        assert marker not in prompt


def test_continuation_prompt_ends_with_the_users_own_words():
    assert build_write_prompt(None, "medium", preceding_text="I started this ").endswith(
        "Write-up:\nI started this "
    )


def test_unknown_length_is_refused():
    with pytest.raises(ValueError):
        build_write_prompt(["a"], "epic")


@pytest.mark.parametrize(
    "words,expected", [(1, "short"), (120, "short"), (121, "medium"), (500, "medium"), (501, "long")]
)
def test_length_buckets(words, expected):
    assert length_bucket(words) == expected


def test_a_budget_cut_ends_at_the_last_whole_sentence():
    """A draft that stops mid-word reads as broken software, not as a draft."""
    from voiceprint.scaffold import trim_to_sentence

    assert trim_to_sentence("First one. Second one. Third is cut off mid") == (
        "First one. Second one."
    )
    assert trim_to_sentence('He said "go." Then the tr') == 'He said "go."'
    assert trim_to_sentence("no terminator anywhere") == "no terminator anywhere"


def test_short_is_capped_to_what_short_means():
    from voiceprint.scaffold import MAX_TOKENS, SHORT_MAX_WORDS, stop_for

    assert MAX_TOKENS["short"] < MAX_TOKENS["medium"]
    assert MAX_TOKENS["short"] <= SHORT_MAX_WORDS * 2
    assert "\n\n" in stop_for("short")
    assert "\n\n" not in stop_for("medium")
