"""Generate LLM summaries for communities (GraphRAG-style retrieval anchors).

Metadata communities get summaries describing what business capability the
cluster of Salesforce objects/automations implements.  Document communities
get summaries describing the topics and processes covered by their chunks.

Summaries are embedded and stored on the Community row for cosine-distance
retrieval at query time.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import ChunkCommunity, Community
from app.services.ai.router import get_embedding_provider, llm_call

logger = logging.getLogger(__name__)

_META_SUMMARY_PROMPT = """\
You are a Salesforce platform analyst. Given the following group of related \
Salesforce metadata items that were clustered by their dependency relationships, \
write a 2-3 sentence summary of what business capability or functional area \
this group implements. Focus on the business purpose, not technical details.

## Cluster Members
{members_text}
"""

_DOC_SUMMARY_PROMPT = """\
You are a business analyst. Given the following group of related document \
sections that were clustered by concept co-occurrence, write a 2-3 sentence \
summary of the main topics, processes, or business areas these sections cover.

## Top Concepts
{concepts}

## Representative Excerpts
{excerpts}
"""


def _describe_metadata_member(node_id: str, obj_map: dict, auto_map: dict) -> str:
    """Build a short text description of a metadata community member node."""
    parts = node_id.split(":", 1)
    if len(parts) != 2:
        return node_id
    node_type, api_name = parts

    if node_type == "object" and api_name in obj_map:
        obj = obj_map[api_name]
        label = obj.label or api_name
        custom = "Custom" if obj.is_custom else "Standard"
        return f"Object: {label} ({api_name}) [{custom}, {obj.record_count:,} records]"

    if node_type in ("flow", "apex_trigger", "validation_rule", "workflow_rule", "approval_process"):
        auto = auto_map.get((node_type if node_type != "apex_trigger" else "trigger", api_name))
        if not auto:
            auto = auto_map.get((node_type, api_name))
        if auto:
            label = auto.label or api_name
            status = auto.status or "unknown"
            return f"{node_type.replace('_', ' ').title()}: {label} ({api_name}) [{status}]"

    if node_type == "apex_class":
        return f"Apex Class: {api_name}"

    return f"{node_type}: {api_name}"


async def summarize_metadata_communities(org_id: UUID, db: AsyncSession) -> int:
    """Generate LLM summaries + embeddings for all metadata communities in an org."""
    from app.models.metadata import MetadataAutomation, MetadataObject

    comms_q = await db.execute(
        select(Community).where(
            Community.org_id == org_id,
            Community.source == "metadata",
            Community.summary.is_(None),
        )
    )
    communities = comms_q.scalars().all()
    if not communities:
        return 0

    objs_q = await db.execute(
        select(MetadataObject).where(MetadataObject.org_id == org_id)
    )
    obj_map = {o.api_name: o for o in objs_q.scalars().all()}

    autos_q = await db.execute(
        select(MetadataAutomation).where(MetadataAutomation.org_id == org_id)
    )
    auto_map = {(a.automation_type, a.api_name): a for a in autos_q.scalars().all()}

    client = get_embedding_provider()
    summarized = 0

    for comm in communities:
        member_lines = []
        for node_id in (comm.member_concept_ids or [])[:30]:
            member_lines.append(_describe_metadata_member(node_id, obj_map, auto_map))

        if not member_lines:
            continue

        members_text = "\n".join(f"- {line}" for line in member_lines)
        prompt = _META_SUMMARY_PROMPT.format(members_text=members_text)

        try:
            result = llm_call(
                prompt=prompt,
                max_tokens=256,
                tier="lite",
                operation="community_summarization",
            )
            comm.summary = result.text.strip()
        except Exception:
            logger.warning("community_summary_failed comm_id=%s", comm.id, exc_info=True)
            continue

        try:
            from app.services.documents.vectorizer import _embed
            embedding = await _embed(client, comm.summary)
            comm.summary_embedding = embedding
        except Exception:
            logger.warning("community_embed_failed comm_id=%s", comm.id, exc_info=True)

        summarized += 1

    await db.flush()
    logger.info("summarize_metadata_communities org_id=%s count=%d", org_id, summarized)
    return summarized


async def summarize_document_communities(org_id: UUID, db: AsyncSession) -> int:
    """Generate LLM summaries + embeddings for all document communities in an org."""
    from app.models.document import DocumentChunk
    from app.models.knowledge import Concept

    comms_q = await db.execute(
        select(Community).where(
            Community.org_id == org_id,
            Community.source == "document",
            Community.summary.is_(None),
        )
    )
    communities = comms_q.scalars().all()
    if not communities:
        return 0

    client = get_embedding_provider()
    summarized = 0

    for comm in communities:
        top_concepts = (comm.metadata_json or {}).get("top_concepts", [])
        concepts_str = ", ".join(top_concepts[:10]) if top_concepts else comm.label or ""

        cc_q = await db.execute(
            select(ChunkCommunity.chunk_id).where(
                ChunkCommunity.community_id == comm.id
            ).limit(5)
        )
        chunk_ids = [row[0] for row in cc_q.all()]

        excerpts = ""
        if chunk_ids:
            chunks_q = await db.execute(
                select(DocumentChunk.content).where(
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.content.isnot(None),
                )
            )
            excerpts = "\n---\n".join(
                (row[0] or "")[:500] for row in chunks_q.all()
            )

        if not concepts_str and not excerpts:
            continue

        prompt = _DOC_SUMMARY_PROMPT.format(
            concepts=concepts_str,
            excerpts=excerpts[:2000],
        )

        try:
            result = llm_call(
                prompt=prompt,
                max_tokens=256,
                tier="lite",
                operation="community_summarization",
            )
            comm.summary = result.text.strip()
        except Exception:
            logger.warning("community_summary_failed comm_id=%s", comm.id, exc_info=True)
            continue

        try:
            from app.services.documents.vectorizer import _embed
            embedding = await _embed(client, comm.summary)
            comm.summary_embedding = embedding
        except Exception:
            logger.warning("community_embed_failed comm_id=%s", comm.id, exc_info=True)

        summarized += 1

    await db.flush()
    logger.info("summarize_document_communities org_id=%s count=%d", org_id, summarized)
    return summarized
