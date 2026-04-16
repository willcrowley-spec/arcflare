"""Adaptive document chunking with token-based splitting.

Chunk sizes vary based on content type:
- Metadata/structured: 256 tokens
- Body text: 512 tokens (default)
- Long narratives: 1024 tokens
"""
import logging
from dataclasses import dataclass

import tiktoken

from app.services.documents.parser import ParsedElement

logger = logging.getLogger(__name__)

enc = tiktoken.get_encoding("cl100k_base")

CHUNK_SIZE_DEFAULT = 512
CHUNK_SIZE_METADATA = 256
CHUNK_SIZE_LARGE = 1024
CHUNK_OVERLAP = 64

_METADATA_TYPES = {"key_value", "list_item", "table"}
_LARGE_TYPES = {"narrative", "code_block"}


@dataclass
class TextChunk:
    document_id: str
    text: str
    chunk_index: int
    section_title: str | None = None
    page_number: int | None = None
    token_count: int = 0


def _get_chunk_size(section_title: str | None, element_type: str | None) -> int:
    if element_type in _METADATA_TYPES:
        return CHUNK_SIZE_METADATA
    if section_title and any(
        kw in section_title.lower()
        for kw in ("salesforce", "metadata", "field", "validation", "permission")
    ):
        return CHUNK_SIZE_METADATA
    if element_type in _LARGE_TYPES:
        return CHUNK_SIZE_LARGE
    return CHUNK_SIZE_DEFAULT


def chunk_document(doc_id: str, elements: list[ParsedElement]) -> list[TextChunk]:
    """Create adaptive chunks from parsed elements."""
    chunks: list[TextChunk] = []
    current_section = None
    current_text = ""
    current_page = None

    for element in elements:
        if element.element_type == "title":
            if len(enc.encode(current_text)) > 30:
                chunks.append(_make_chunk(doc_id, current_text, len(chunks), current_section, current_page))
            current_section = element.text
            current_text = f"{element.text}\n\n"
            current_page = element.page_number
        else:
            chunk_size = _get_chunk_size(current_section, element.element_type)
            candidate = current_text + element.text + "\n\n"

            if len(enc.encode(candidate)) > chunk_size:
                if current_text.strip():
                    chunks.append(_make_chunk(doc_id, current_text, len(chunks), current_section, current_page))
                overlap_text = _get_overlap(current_text)
                current_text = overlap_text + element.text + "\n\n"
            else:
                current_text = candidate

            if element.page_number:
                current_page = element.page_number

    if current_text.strip() and len(enc.encode(current_text)) > 15:
        chunks.append(_make_chunk(doc_id, current_text, len(chunks), current_section, current_page))

    logger.info("chunking_complete doc=%s chunks=%d", doc_id, len(chunks))
    return chunks


def _make_chunk(doc_id: str, text: str, index: int, section: str | None, page: int | None) -> TextChunk:
    return TextChunk(
        document_id=doc_id,
        text=text.strip(),
        chunk_index=index,
        section_title=section,
        page_number=page,
        token_count=len(enc.encode(text)),
    )


def _get_overlap(text: str) -> str:
    tokens = enc.encode(text)
    overlap_tokens = tokens[-CHUNK_OVERLAP:]
    overlap_text = enc.decode(overlap_tokens)
    for sep in [". ", ".\n", "\n\n", "\n"]:
        idx = overlap_text.find(sep)
        if idx != -1 and idx < len(overlap_text) - 10:
            return overlap_text[idx + len(sep):]
    return overlap_text + "\n"
