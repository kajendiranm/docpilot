"""Read markdown files from a folder."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ingest.chunker import iter_headings


@dataclass(frozen=True)
class LoadedDoc:
    path: str  # relative to the ingest folder, e.g. "setup-guide.md"
    title: str
    text: str
    content_hash: str  # sha256 of the file bytes; unchanged hash = skip re-embedding


def extract_title(text: str, fallback: str) -> str:
    """The first level-1 heading (outside code blocks), else the fallback."""
    for level, heading in iter_headings(text):
        if level == 1:
            return heading
    return fallback


def load_markdown_files(folder: Path) -> list[LoadedDoc]:
    docs = []
    for file in sorted(folder.rglob("*.md")):  # sorted -> same order every run
        raw = file.read_bytes()
        text = raw.decode("utf-8")
        docs.append(
            LoadedDoc(
                path=file.relative_to(folder).as_posix(),
                title=extract_title(text, fallback=file.stem),
                text=text,
                content_hash=hashlib.sha256(raw).hexdigest(),
            )
        )
    return docs
