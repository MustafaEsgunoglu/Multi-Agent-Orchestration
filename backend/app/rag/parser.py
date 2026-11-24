"""Lightweight document parser using PyMuPDF (fitz) — zero heavy ML/OCR footprint."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int
    metadata: dict[str, str]


def parse_document_bytes(
    data: bytes,
    *,
    filename: str,
    content_type: str | None = None,
) -> ParsedDocument:
    """Extract clean text from PDF (via PyMuPDF) or plain-text/Markdown bytes."""
    lower_name = filename.lower()
    is_pdf = lower_name.endswith(".pdf") or (content_type or "").lower() == "application/pdf"

    if is_pdf:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages: list[str] = []
            for page in doc:
                extracted = page.get_text("text").strip()
                if extracted:
                    pages.append(extracted)
            raw_meta = doc.metadata or {}
            clean_meta = {
                str(k): str(v) for k, v in raw_meta.items() if v is not None and str(v).strip()
            }
            return ParsedDocument(
                text="\n\n".join(pages),
                page_count=len(doc),
                metadata=clean_meta,
            )

    text = data.decode("utf-8", errors="replace").strip()
    return ParsedDocument(text=text, page_count=1, metadata={"filename": filename})
