"""Heading-aware markdown chunking.

1. Split the document at markdown headings, so every chunk belongs to one section.
2. Split long sections into ~max_tokens chunks, each starting with ~overlap_tokens
   from the end of the previous chunk so an idea cut at a boundary is not lost.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")

CHARS_PER_TOKEN = 4  # rough average for English text; good enough for sizing chunks


@dataclass(frozen=True)
class Chunk:
    section: str
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def _lines_with_headings(text: str) -> Iterator[tuple[str, tuple[int, str] | None]]:
    """Yield (line, (level, heading) or None). '#' lines inside code fences are not headings."""
    in_code = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_code = not in_code
            yield line, None
            continue
        match = None if in_code else HEADING_RE.match(line)
        yield line, (len(match.group(1)), match.group(2)) if match else None


def iter_headings(text: str) -> Iterator[tuple[int, str]]:
    for _, heading in _lines_with_headings(text):
        if heading:
            yield heading


def split_sections(text: str, title: str) -> list[tuple[str, str]]:
    """Return (section heading, body) pairs. Text before the first sub-heading uses the title."""
    sections: list[tuple[str, list[str]]] = [(title, [])]
    first_heading = True
    for line, heading in _lines_with_headings(text):
        if heading is None:
            sections[-1][1].append(line)
            continue
        if not (first_heading and heading[0] == 1):  # skip the document's own H1 title
            sections.append((heading[1], []))
        first_heading = False
    return [(name, body) for name, lines in sections if (body := "\n".join(lines).strip())]


def _tail(text: str, max_chars: int) -> str:
    """The last ~max_chars of text, starting at a word boundary."""
    if len(text) <= max_chars:
        return text
    cut = text[-max_chars:]
    space = cut.find(" ")
    return cut[space + 1 :] if space != -1 else cut


def _split_long(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    # Paragraphs are the natural split points. A paragraph that is too long on its own
    # is cut into word windows.
    units: list[str] = []
    for para in PARAGRAPH_BREAK_RE.split(text):
        if len(para) <= max_chars:
            units.append(para)
            continue
        current = ""
        for word in para.split():
            if current and len(current) + 1 + len(word) > max_chars - overlap_chars:
                units.append(current)
                current = word
            else:
                current = f"{current} {word}" if current else word
        if current:
            units.append(current)

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = f"{_tail(current, overlap_chars)}\n\n{unit}"
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_markdown(
    text: str, title: str, max_tokens: int = 450, overlap_tokens: int = 50
) -> list[Chunk]:
    chunks = []
    for section, body in split_sections(text, title):
        for piece in _split_long(body, max_tokens, overlap_tokens):
            chunks.append(Chunk(section=section, content=piece, token_count=estimate_tokens(piece)))
    return chunks
