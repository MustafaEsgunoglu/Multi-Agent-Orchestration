"""Recursive text chunker for low-RAM RAG ingestion."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")


@dataclass(frozen=True, slots=True)
class TextChunk:
    index: int
    content: str
    char_start: int
    char_end: int


def _split_recursive(text: str, chunk_size: int, separators: tuple[str, ...]) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    sep = separators[0]
    remaining_seps = separators[1:]

    if sep == "":
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    parts = text.split(sep)
    if len(parts) == 1:
        return _split_recursive(text, chunk_size, remaining_seps)

    merged: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                merged.append(current)
            if len(part) > chunk_size:
                merged.extend(_split_recursive(part, chunk_size, remaining_seps))
                current = ""
            else:
                current = part
    if current:
        merged.append(current)
    return merged


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[TextChunk]:
    """Split text recursively into overlapping chunks suitable for API embeddings."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size.")

    cleaned = text.strip()
    if not cleaned:
        return []

    raw_pieces = _split_recursive(cleaned, chunk_size, DEFAULT_SEPARATORS)
    chunks: list[TextChunk] = []
    cursor = 0

    for idx, piece in enumerate(raw_pieces):
        content = piece.strip()
        if not content:
            continue
        if idx > 0 and chunk_overlap > 0 and chunks:
            prev_tail = chunks[-1].content[-chunk_overlap:]
            if prev_tail and not content.startswith(prev_tail):
                content = f"{prev_tail} {content}".strip()

        start = cleaned.find(piece.strip(), max(0, cursor - chunk_overlap))
        if start == -1:
            start = cursor
        end = start + len(piece.strip())
        cursor = end

        chunks.append(
            TextChunk(index=len(chunks), content=content, char_start=start, char_end=end)
        )

    return chunks
