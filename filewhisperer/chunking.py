"""Split long text into overlapping chunks so retrieval can work on pieces
small enough to be precise, with enough overlap that context isn't lost at
chunk boundaries.

Chunking happens per-page (see chunk_document()) so a chunk never spans a
page boundary — that's what makes an accurate "page 3" citation possible
later. A page that's itself longer than chunk_size still gets split into
multiple chunks, all labeled with that same page.
"""

from __future__ import annotations

from dataclasses import dataclass

from .loaders import Page

DEFAULT_CHUNK_SIZE = 1400
DEFAULT_OVERLAP = 200


@dataclass
class Chunk:
    doc_name: str
    index: int
    text: str
    page: str | None = None  # e.g. "page 3", "Sheet1 (rows 1-100)", or None


def _chunk_one_page(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split a single page's text on paragraph boundaries where possible,
    packing paragraphs into ~chunk_size character windows with `overlap`
    characters repeated between consecutive chunks. Returns plain strings;
    chunk_document() wraps these into Chunk objects with doc/page metadata."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    pieces: list[str] = []
    current = ""

    def flush():
        if current.strip():
            pieces.append(current.strip())

    for para in paragraphs:
        if len(para) > chunk_size:
            # A single paragraph longer than the chunk size (e.g. a dense
            # table dump) gets hard-split on its own.
            if current:
                flush()
                current = ""
            for start in range(0, len(para), chunk_size - overlap):
                pieces.append(para[start : start + chunk_size])
            continue

        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > chunk_size:
            flush()
            tail = current[-overlap:] if current else ""
            current = f"{tail}\n\n{para}".strip() if tail else para
        else:
            current = candidate

    flush()
    return pieces


def chunk_document(
    doc_name: str,
    pages: list[Page],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Chunk every page of a document, keeping each chunk within a single
    page so it can be cited accurately."""
    chunks: list[Chunk] = []
    for page in pages:
        for piece in _chunk_one_page(page.text, chunk_size, overlap):
            chunks.append(Chunk(doc_name=doc_name, index=len(chunks), text=piece, page=page.label))
    return chunks


def chunk_text(
    doc_name: str,
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Back-compat convenience wrapper for chunking a single flat string
    with no page information (page=None on every resulting chunk)."""
    return chunk_document(doc_name, [Page(label=None, text=text)], chunk_size, overlap)
