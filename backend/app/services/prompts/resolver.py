"""Resolve merged prompt blocks for operations (system defaults + org overrides)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import PromptBlock
from app.services.prompts.registry import (
    get_block_meta,
    get_registry_for_operation,
    get_required_vars,
)

_CACHE_TTL_SEC = 60.0
_merged_cache: dict[tuple[str, str], tuple[float, list["_MergedBlock"]]] = {}


@dataclass(frozen=True)
class _MergedBlock:
    block_type: str
    content: str
    version: int
    is_customized: bool


def _cache_key(operation_id: str, org_id: UUID | None) -> tuple[str, str]:
    org_part = str(org_id) if org_id is not None else "__system__"
    return (operation_id, org_part)


def _cache_get(key: tuple[str, str]) -> list[_MergedBlock] | None:
    entry = _merged_cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        del _merged_cache[key]
        return None
    return value


def _cache_set(key: tuple[str, str], value: list[_MergedBlock]) -> None:
    _merged_cache[key] = (time.monotonic() + _CACHE_TTL_SEC, value)


def _invalidate_cache(operation_id: str, org_id: UUID | None) -> None:
    key = _cache_key(operation_id, org_id)
    _merged_cache.pop(key, None)


async def _load_merged_blocks(
    db: AsyncSession,
    operation_id: str,
    org_id: UUID | None,
) -> list[_MergedBlock]:
    registry = get_registry_for_operation(operation_id)
    if not registry:
        return []

    base_filters = [
        PromptBlock.operation_id == operation_id,
        PromptBlock.status == "active",
    ]
    if org_id is not None:
        stmt = select(PromptBlock).where(
            and_(
                *base_filters,
                or_(PromptBlock.org_id.is_(None), PromptBlock.org_id == org_id),
            )
        )
    else:
        stmt = select(PromptBlock).where(and_(*base_filters, PromptBlock.org_id.is_(None)))

    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    org_by_type: dict[str, PromptBlock] = {}
    system_by_type: dict[str, PromptBlock] = {}
    for row in rows:
        if row.org_id is not None:
            org_by_type[row.block_type] = row
        else:
            system_by_type[row.block_type] = row

    merged: list[_MergedBlock] = []
    for block_def in registry:
        block_type = block_def["type"]
        org_row = org_by_type.get(block_type) if org_id is not None else None
        system_row = system_by_type.get(block_type)

        if org_row is not None:
            merged.append(
                _MergedBlock(
                    block_type=block_type,
                    content=org_row.content,
                    version=org_row.version,
                    is_customized=True,
                )
            )
        elif system_row is not None:
            merged.append(
                _MergedBlock(
                    block_type=block_type,
                    content=system_row.content,
                    version=system_row.version,
                    is_customized=False,
                )
            )
        else:
            merged.append(
                _MergedBlock(
                    block_type=block_type,
                    content="",
                    version=0,
                    is_customized=False,
                )
            )
    return merged


async def resolve_prompt_blocks(
    operation_id: str,
    org_id: UUID | None,
    db: AsyncSession,
) -> dict[str, str]:
    key = _cache_key(operation_id, org_id)
    cached = _cache_get(key)
    if cached is not None:
        return {b.block_type: b.content for b in cached}

    merged = await _load_merged_blocks(db, operation_id, org_id)
    _cache_set(key, merged)
    return {b.block_type: b.content for b in merged}


async def resolve_prompt_blocks_with_meta(
    operation_id: str,
    org_id: UUID | None,
    db: AsyncSession,
) -> list[dict]:
    key = _cache_key(operation_id, org_id)
    cached = _cache_get(key)
    if cached is None:
        cached = await _load_merged_blocks(db, operation_id, org_id)
        _cache_set(key, cached)

    out: list[dict] = []
    for row in cached:
        meta = get_block_meta(operation_id, row.block_type) or {}
        label = meta.get("label", row.block_type)
        editable = bool(meta.get("editable", False))
        required = list(meta.get("required_vars", []))
        out.append(
            {
                "block_type": row.block_type,
                "label": label,
                "editable": editable,
                "content": row.content,
                "is_customized": row.is_customized,
                "is_locked": not editable,
                "available_vars": required,
                "version": row.version,
            }
        )
    return out


def validate_required_vars(content: str, operation_id: str, block_type: str) -> list[str]:
    required = get_required_vars(operation_id, block_type)
    missing: list[str] = []
    for var_name in required:
        pattern = re.compile(r"\{" + re.escape(var_name) + r"\}")
        if not pattern.search(content):
            missing.append(var_name)
    return missing
