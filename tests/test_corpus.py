import pytest

from voiceprint import corpus, markdown

ESSAY = """---
title: something
---

# A heading

The first paragraph says a thing, and it says it in a way that only one person
would have said it, which is the entire point of the exercise.

```python
print("not my voice")
```

| a | b |
| - | - |

> someone else said this

The second paragraph carries on, because the writer is not finished and rarely is.
"""


def words(count: int) -> str:
    """`count` words of sentence-shaped filler. Fragments without a sentence in
    them are dropped by the corpus reader, so fixtures have to be real prose."""
    sentence = "the writer said a thing about it. "
    return (sentence * (count // 7 + 1)).strip()


def test_prose_only_drops_everything_that_is_not_voice():
    prose = markdown.prose_only(ESSAY)
    assert "The first paragraph" in prose
    assert "The second paragraph" in prose
    for artifact in ("title: something", "# A heading", "print(", "| a | b |", "> someone else"):
        assert artifact not in prose


def test_segment_preserves_every_character():
    assert "".join(text for _, text in markdown.segment(ESSAY)) == ESSAY


def test_short_documents_stay_whole(tmp_path):
    """A 60-word email is a real sample of how someone writes short things.
    Merging it into a 250-word block would destroy the short-form signal."""
    note = words(60)
    (tmp_path / "note.md").write_text(note)
    (tmp_path / "other.md").write_text(words(400))

    chunks = corpus.to_chunks(corpus.read_path(tmp_path))
    short = [c for c in chunks if c.source == "note.md"]
    assert len(short) == 1
    assert short[0].length == "short"


def test_long_documents_split_on_paragraph_boundaries(tmp_path):
    paragraph = words(100)
    (tmp_path / "long.md").write_text(
        "\n\n".join(f"Paragraph {index}. {paragraph}" for index in range(8))
    )

    chunks = corpus.to_chunks(corpus.read_path(tmp_path))
    assert len(chunks) > 1
    assert all(c.words <= 400 for c in chunks)
    assert all("\n\n" in c.text or c.words <= 250 for c in chunks)


def test_a_corpus_too_small_to_learn_from_is_refused(tmp_path):
    (tmp_path / "tiny.md").write_text(words(50))
    chunks = corpus.to_chunks(corpus.read_path(tmp_path))
    with pytest.raises(corpus.CorpusTooSmall):
        corpus.check_size(chunks)


def test_a_thin_corpus_warns_but_proceeds(tmp_path):
    (tmp_path / "thin.md").write_text(words(400))
    chunks = corpus.to_chunks(corpus.read_path(tmp_path))
    assert "thin" in corpus.check_size(chunks)


def test_a_healthy_corpus_says_nothing(tmp_path):
    (tmp_path / "ok.md").write_text(words(1500))
    chunks = corpus.to_chunks(corpus.read_path(tmp_path))
    assert corpus.check_size(chunks) is None


def test_missing_path_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        corpus.read_path(tmp_path / "nope")


def test_folder_without_text_files_fails_loudly(tmp_path):
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    with pytest.raises(FileNotFoundError):
        corpus.read_path(tmp_path)


def test_outline_fragments_are_not_a_voice(tmp_path):
    """A notes app is half bulleted thinking-out-loud. Training on it produces a
    model that writes in bullets."""
    prose = words(200)
    outline = "\n".join(f"- point {i}" for i in range(30))
    (tmp_path / "mixed.md").write_text(f"{outline}\n\n{prose}")

    chunks = corpus.to_chunks(corpus.read_path(tmp_path))
    assert chunks
    assert all("- point" not in c.text for c in chunks)


def test_a_file_of_pure_outline_yields_nothing(tmp_path):
    (tmp_path / "notes.md").write_text("\n".join(f"- thought {i}" for i in range(50)))
    assert corpus.to_chunks(corpus.read_path(tmp_path)) == []


def test_duplicate_passages_are_removed_before_training(tmp_path):
    passage = words(400)
    (tmp_path / "first.md").write_text(passage)
    (tmp_path / "copy.md").write_text(passage)

    documents = corpus.read_path(tmp_path)
    chunks = corpus.to_chunks(documents)
    report = corpus.inspect(documents)

    assert sum(chunk.words for chunk in chunks) < 500
    assert report.duplicate_chunks > 0
    assert report.duplicate_words > 0
    assert any("duplicate" in warning for warning in report.warnings)


def test_hosted_preflight_blocks_checkout_for_a_marginal_corpus(tmp_path):
    (tmp_path / "thin.md").write_text(words(800))

    report = corpus.inspect_hosted(corpus.read_path(tmp_path))

    assert report.status == "blocked"
    assert report.ready is False
    assert report.minimum_words == corpus.HOSTED_MIN_CORPUS_WORDS
    assert any("at least 1000" in reason for reason in report.reasons)


def test_hosted_preflight_warns_but_allows_a_usable_corpus(tmp_path):
    (tmp_path / "usable.md").write_text(words(1500))

    report = corpus.inspect_hosted(corpus.read_path(tmp_path))

    assert report.status == "warning"
    assert report.ready is True
    assert report.usable_words >= 1000
    assert any("2000+" in warning for warning in report.warnings)


def test_hosted_preflight_marks_a_strong_corpus_ready(tmp_path):
    (tmp_path / "strong.md").write_text(words(2500))

    report = corpus.inspect_hosted(corpus.read_path(tmp_path))

    assert report.status == "ready"
    assert report.ready is True
    assert report.reasons == ()
    assert report.warnings == ()
