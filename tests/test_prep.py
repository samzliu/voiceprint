from voiceprint.corpus import Chunk
from voiceprint.prep import continuation_split, pairs_for_chunk, parse_notes

BODY = (
    "The first sentence sets it up. The second one turns it. The third lands somewhere "
    "the reader did not expect. The fourth cleans up after the third."
)


def chunk(text=BODY):
    return Chunk(text=text, words=len(text.split()), length="medium", source="t.md")


def test_parse_notes_takes_bullets_and_drops_preamble():
    raw = "Here are the notes:\n- first point\n* second point\n3. third point\n"
    assert parse_notes(raw) == ["first point", "second point", "third point"]


def test_parse_notes_returns_nothing_when_the_model_ignored_the_format():
    assert parse_notes("I'm afraid I can't summarize that passage.") == []


def test_continuation_split_lands_on_a_sentence_boundary():
    head, tail = continuation_split(BODY)
    assert head.endswith(".")
    assert BODY.startswith(head)
    assert tail
    assert head + " " + tail == BODY


def test_continuation_split_declines_on_a_single_sentence():
    head, tail = continuation_split("Only one sentence here")
    assert head == ""
    assert tail == "Only one sentence here"


def test_every_chunk_yields_all_three_pair_kinds():
    pairs = pairs_for_chunk(chunk(), ["a note"], "bland version")
    assert {p.kind for p in pairs} == {"write", "continue", "rewrite"}
    assert all(p.completion.strip() for p in pairs)


def test_a_chunk_without_usable_notes_still_teaches_continuation_and_rewrite():
    """A malformed brief drops that one pair rather than training on garbage."""
    kinds = {p.kind for p in pairs_for_chunk(chunk(), [], "bland version")}
    assert kinds == {"continue", "rewrite"}


def test_a_continuation_pair_puts_the_head_in_the_assistant_turn():
    """The model continues its own half-written answer. Putting the head in the
    user turn instead would train it to quote the prompt back."""
    pairs = {p.kind: p for p in pairs_for_chunk(chunk(), ["a note"], "bland version")}
    head = pairs["continue"].prompt.prefill
    assert head.strip()
    assert BODY.startswith(head.strip())
    assert head.strip() not in pairs["continue"].prompt.messages[0]["content"]
    assert head + pairs["continue"].completion == BODY


def test_write_and_rewrite_pairs_complete_to_the_authors_real_text():
    pairs = {p.kind: p for p in pairs_for_chunk(chunk(), ["a note"], "bland version")}
    assert pairs["write"].completion == BODY
    assert pairs["rewrite"].completion == BODY
    # The rewrite pair has to *show* the model the text it is rewriting, so the
    # degraded draft lands in the user turn rather than in notes about it.
    assert "bland version" in pairs["rewrite"].prompt.messages[0]["content"]
