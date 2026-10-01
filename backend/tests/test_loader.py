from pathlib import Path

from ingest.loader import extract_title, load_markdown_files


def test_loads_only_markdown_with_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Alpha\n\nText")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("No heading here")
    (tmp_path / "notes.txt").write_text("ignored")

    docs = load_markdown_files(tmp_path)

    assert [d.path for d in docs] == ["a.md", "sub/b.md"]
    assert [d.title for d in docs] == ["Alpha", "b"]  # falls back to file name


def test_hash_changes_only_when_content_changes(tmp_path: Path) -> None:
    file = tmp_path / "a.md"
    file.write_text("# A\n\nv1")
    first = load_markdown_files(tmp_path)[0].content_hash
    assert load_markdown_files(tmp_path)[0].content_hash == first

    file.write_text("# A\n\nv2")
    assert load_markdown_files(tmp_path)[0].content_hash != first


def test_title_ignores_hash_lines_in_code() -> None:
    text = "```\n# not a title\n```\n# Real Title\n"
    assert extract_title(text, fallback="x") == "Real Title"
