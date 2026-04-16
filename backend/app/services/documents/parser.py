"""Parse uploaded files into text chunks."""

from pathlib import Path


def parse_document(file_path: str) -> list[dict]:
    """
    Parse a document on disk into chunk dicts with text and optional page/section hints.

    Uses extension-based routing; extend with unstructured loaders as needed.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    if not text.strip() and suffix in {".docx", ".pptx", ".xlsx"}:
        # TODO: wire unstructured.partition for Office formats when available in runtime.
        text = f"[binary {suffix} placeholder — enable unstructured loaders]"
    chunks: list[dict] = []
    max_chunk = 4000
    idx = 0
    for i in range(0, len(text), max_chunk):
        chunks.append(
            {
                "chunk_index": idx,
                "content": text[i : i + max_chunk],
                "page_number": None,
                "section_title": None,
                "metadata_json": {},
            }
        )
        idx += 1
    return chunks
