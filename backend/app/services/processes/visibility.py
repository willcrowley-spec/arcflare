"""Visibility helpers for process discovery metadata inputs."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataObject


def is_visible_metadata_object(obj: Any) -> bool:
    """Return whether a metadata object can seed discovery evidence."""
    return getattr(obj, "classification", None) != "excluded"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_for_match(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return " ".join(part for part in normalized.split() if part)


def _api_variants(value: str) -> set[str]:
    api_name = _text(value)
    if not api_name:
        return set()
    variants = {api_name}
    parts = api_name.split("__", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        variants.add(parts[1])
    stem = api_name
    for suffix in ("__c", "__e", "__mdt", "__cio"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if "__" in stem:
        stem = stem.split("__", 1)[1]
    if stem:
        variants.add(stem)
        variants.add(stem.replace("_", " "))
    return variants


def hidden_metadata_terms_from_objects(objects: list[Any]) -> set[str]:
    """Build exact and human-readable terms that should not enter discovery prompts."""
    terms: set[str] = set()
    for obj in objects:
        terms.update(_api_variants(getattr(obj, "api_name", "")))
        label = _text(getattr(obj, "label", ""))
        if label:
            terms.add(label)
            terms.add(label.replace(" ", "_"))
    return {term for term in terms if term}


def text_mentions_hidden_metadata(text: str, hidden_terms: set[str]) -> bool:
    """Return whether text contains an excluded object's API or label variant."""
    if not text or not hidden_terms:
        return False
    normalized_text = _normalize_for_match(text)
    raw_lower = text.lower()
    for term in hidden_terms:
        normalized_term = _normalize_for_match(term)
        if normalized_term and normalized_term in normalized_text:
            return True
        if term.lower() in raw_lower:
            return True
    return False


def redact_hidden_metadata_text(text: str, hidden_terms: set[str]) -> str:
    """Remove evidence lines that mention excluded metadata objects."""
    if not text or not hidden_terms:
        return text or ""
    lines = [
        line
        for line in str(text).splitlines()
        if not text_mentions_hidden_metadata(line, hidden_terms)
    ]
    return "\n".join(lines).strip()


def metadata_object_visible_clause():
    """SQLAlchemy clause matching objects not hidden by classification."""
    return sa.or_(
        MetadataObject.classification.is_(None),
        MetadataObject.classification != "excluded",
    )


async def visible_object_names(
    org_id: UUID,
    db: AsyncSession,
    object_names: Iterable[str],
) -> set[str]:
    """Return the subset of object API names visible to discovery."""
    names = sorted({str(name) for name in object_names if str(name or "").strip()})
    if not names:
        return set()
    result = await db.execute(
        select(MetadataObject.api_name).where(
            MetadataObject.org_id == org_id,
            MetadataObject.api_name.in_(names),
            metadata_object_visible_clause(),
        )
    )
    return {str(row[0]) for row in result.all()}


async def hidden_metadata_terms(org_id: UUID, db: AsyncSession) -> set[str]:
    """Return hidden metadata API/label terms for an org."""
    result = await db.execute(
        select(MetadataObject).where(
            MetadataObject.org_id == org_id,
            MetadataObject.classification == "excluded",
        )
    )
    return hidden_metadata_terms_from_objects(list(result.scalars().all()))


async def filter_visible_object_names(
    org_id: UUID,
    db: AsyncSession,
    object_names: Iterable[str],
) -> list[str]:
    """Filter object names while preserving caller order."""
    names = [str(name) for name in object_names if str(name or "").strip()]
    visible = await visible_object_names(org_id, db, names)
    return [name for name in names if name in visible]
