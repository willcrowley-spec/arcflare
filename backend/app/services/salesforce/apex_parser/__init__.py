"""ANTLR4-generated Apex parser helpers."""

from antlr4 import InputStream


class CaseInsensitiveInputStream(InputStream):
    """Lowercases Apex source before lexing (Apex is case-insensitive)."""

    def __init__(self, data: str) -> None:
        super().__init__(data.lower())


__all__ = ["CaseInsensitiveInputStream"]
