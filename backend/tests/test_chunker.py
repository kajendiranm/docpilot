from ingest.chunker import (
    CHARS_PER_TOKEN,
    chunk_markdown,
    estimate_tokens,
    iter_headings,
    split_sections,
)

DOC = """# Setup Guide

Intro paragraph.

## Getting the code

```bash
git clone repo
# this is a bash comment, not a heading
```

## Empty section

## Running tests

Run pytest.
"""


def test_splits_at_headings_and_keeps_section_names() -> None:
    sections = split_sections(DOC, title="Setup Guide")
    assert [name for name, _ in sections] == ["Setup Guide", "Getting the code", "Running tests"]


def test_text_before_first_subheading_uses_title() -> None:
    sections = dict(split_sections(DOC, title="Setup Guide"))
    assert sections["Setup Guide"] == "Intro paragraph."


def test_hash_lines_inside_code_blocks_are_not_headings() -> None:
    headings = [h for _, h in iter_headings(DOC)]
    assert "this is a bash comment, not a heading" not in headings
    body = dict(split_sections(DOC, title="Setup Guide"))["Getting the code"]
    assert "# this is a bash comment" in body


def test_empty_sections_are_dropped() -> None:
    names = [c.section for c in chunk_markdown(DOC, title="Setup Guide")]
    assert "Empty section" not in names


def test_short_section_is_one_chunk() -> None:
    chunks = chunk_markdown(DOC, title="Setup Guide")
    assert [c.content for c in chunks if c.section == "Running tests"] == ["Run pytest."]


def _long_doc(paragraphs: int) -> str:
    body = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(paragraphs))
    return f"# Big\n\n## Long section\n\n{body}\n"


def test_long_section_is_split_within_size_limit() -> None:
    chunks = chunk_markdown(_long_doc(40), title="Big", max_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1
    assert all(c.section == "Long section" for c in chunks)
    # Each chunk may exceed max by at most the overlap it carries over.
    assert all(len(c.content) <= (200 + 20) * CHARS_PER_TOKEN for c in chunks)


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_markdown(_long_doc(40), title="Big", max_tokens=200, overlap_tokens=20)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        overlap = nxt.content.split("\n\n")[0]
        assert overlap and prev.content.endswith(overlap)


def test_no_text_is_lost() -> None:
    chunks = chunk_markdown(_long_doc(40), title="Big", max_tokens=200, overlap_tokens=20)
    joined = " ".join(c.content for c in chunks)
    for i in range(40):
        assert f"Paragraph {i} " in joined


def test_single_huge_paragraph_is_split_by_words() -> None:
    doc = "# Big\n\n## One block\n\n" + "word " * 3000
    chunks = chunk_markdown(doc, title="Big", max_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1
    assert all(len(c.content) <= (200 + 20) * CHARS_PER_TOKEN for c in chunks)


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100
