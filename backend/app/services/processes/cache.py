"""Prompt-hash-based LLM response cache for the discovery pipeline.

Caches LLM responses keyed by SHA-256 of the full prompt text + operation + model.
Cache invalidation is automatic: any change to metadata, documents, or prompt
templates changes the prompt content → different hash → cache miss.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cache import DiscoveryCache
from app.services.ai.router import LLMResult, PromptParts, _provider_from_model

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS = 24


def _hash_prompt(prompt: str | PromptParts, operation: str, model: str) -> str:
    flat = prompt.as_flat() if isinstance(prompt, PromptParts) else prompt
    payload = f"{operation}::{model}::{flat}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def cache_get(
    org_id: UUID,
    db: AsyncSession,
    prompt: str | PromptParts,
    operation: str,
    model: str,
) -> LLMResult | None:
    """Check cache for a matching prompt hash. Returns None on miss."""
    prompt_hash = _hash_prompt(prompt, operation, model)
    now = datetime.now(tz=timezone.utc)

    row = (
        await db.execute(
            select(DiscoveryCache).where(
                DiscoveryCache.org_id == org_id,
                DiscoveryCache.prompt_hash == prompt_hash,
                DiscoveryCache.operation == operation,
                DiscoveryCache.expires_at > now,
            ).limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return None

    provider = _provider_from_model(model)
    logger.info(
        "cache_hit org_id=%s operation=%s hash=%s age_min=%.0f",
        org_id, operation, prompt_hash[:12],
        (now - row.created_at).total_seconds() / 60,
    )
    return LLMResult(
        text=row.response_text,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        model=model,
        provider=provider,
    )


async def cache_put(
    org_id: UUID,
    db: AsyncSession,
    prompt: str | PromptParts,
    operation: str,
    model: str,
    result: LLMResult,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> None:
    """Store an LLM response in the cache."""
    prompt_hash = _hash_prompt(prompt, operation, model)
    now = datetime.now(tz=timezone.utc)

    entry = DiscoveryCache(
        org_id=org_id,
        prompt_hash=prompt_hash,
        operation=operation,
        model=model,
        response_text=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(entry)
    logger.info(
        "cache_put org_id=%s operation=%s hash=%s ttl_h=%d",
        org_id, operation, prompt_hash[:12], ttl_hours,
    )


async def cache_invalidate_org(org_id: UUID, db: AsyncSession) -> int:
    """Delete all cached responses for an org (e.g., after metadata re-sync)."""
    result = await db.execute(
        delete(DiscoveryCache).where(DiscoveryCache.org_id == org_id)
    )
    count = result.rowcount
    if count:
        logger.info("cache_invalidated org_id=%s entries=%d", org_id, count)
    return count


async def cache_cleanup_expired(db: AsyncSession) -> int:
    """Remove expired cache entries across all orgs."""
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        delete(DiscoveryCache).where(DiscoveryCache.expires_at <= now)
    )
    return result.rowcount
