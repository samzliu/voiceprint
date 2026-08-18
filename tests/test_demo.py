import pytest

from voiceprint.modal_app import parse_demo_brief


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
