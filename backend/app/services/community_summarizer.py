"""Generate LLM summaries for communities (GraphRAG-style retrieval anchors).

Metadata communities get summaries describing what business capability the
cluster of Salesforce objects/automations implements.  Document communities
get summaries describing the topics and processes covered by their chunks.

Summaries are embedded and stored on the Community row for cosine-distance
retrieval at query time.  Hierarchical communities get level-appropriate
summaries: leaf nodes get operational detail, intermediate parents get
capability rollups, and root parents (level 0) get strategic summaries.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import ChunkCommunity, Community
from app.services.ai.router import get_embedding_provider, llm_call

logger = logging.getLogger(__name__)

_META_L0_PROMPT = """\
You are a Salesforce platform analyst. Given the following group of related \
Salesforce metadata items clustered by dependency relationships, write a 3-4 \
sentence OPERATIONAL summary covering:
1. What data flows through this cluster
2. What automations execute and on what triggers
3. What business events or user actions initiate activity here
4. The overall operational pattern (CRUD-heavy, approval-heavy, integration-focused, etc.)

Be specific — name objects, flows, and triggers. Start with a short label phrase.

## Cluster Members
{members_text}
"""

_META_L1_PROMPT = """\
You are a Salesforce platform analyst. Given the following operational \
summaries from sub-clusters, write a 2-3 sentence BUSINESS CAPABILITY summary \
describing what business function this group of clusters implements together.
Focus on the business capability, not implementation details.
Start with a short label phrase (e.g. "Lead Qualification and Scoring").

## Sub-Cluster Summaries
{child_summaries}
"""

_META_L2_PROMPT = """\
You are a strategic business analyst. Given the following capability summaries, \
write a 1-2 sentence STRATEGIC DOMAIN summary suitable for executive-level reporting.
Name the business domain and its strategic importance.

## Capability Summaries
{child_summaries}
"""

_DOC_SUMMARY_PROMPT = """\
You are a business analyst. Given the following group of related document \
sections that were clustered by concept co-occurrence, write a 2-3 sentence \
summary of the main topics, processes, or business areas these sections cover.

## Top Concepts
{concepts}
{excerpts_section}"""

_DOC_L1_PROMPT = """\
You are a business analyst. Given the following operational summaries from \
document sub-clusters, write a 2-3 sentence summary describing the broader \
topic area these clusters cover together.

## Sub-Cluster Summaries
{child_summaries}
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


def _extract_label_from_summary(summary: str, fallback: str) -> str:
    """Extract a short label from the first sentence of a summary."""
    first_line = summary.split(".")[0].strip()
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."
    return first_line if first_line else fallback


async def summarize_metadata_communities(org_id: UUID, db: AsyncSession) -> int:
    """Generate LLM summaries + embeddings for all metadata communities in an org.

    Processes level-0 (leaf) communities first, then builds level-1 and level-2
    summaries from their children's summaries.
    """
    from app.models.metadata import MetadataAutomation, MetadataObject

    comms_q = await db.execute(
        select(Community).where(
            Community.org_id == org_id,
            Community.source == "metadata",
            Community.summary.is_(None),
        ).order_by(Community.level.desc())
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
    comm_summary_cache: dict[UUID, str] = {}

    by_level: dict[int, list[Community]] = {}
    for c in communities:
        by_level.setdefault(c.level, []).append(c)

    for level in sorted(by_level.keys(), reverse=True):
        for comm in by_level[level]:
            children_q = await db.execute(
                select(Community).where(Community.parent_id == comm.id)
            )
            children = children_q.scalars().all()
            child_summaries = [
                comm_summary_cache.get(c.id, c.summary or "")
                for c in children if c.id in comm_summary_cache or c.summary
            ]

            if child_summaries:
                child_text = "\n\n".join(f"- {s}" for s in child_summaries)
                if level == 0 and not comm.parent_id:
                    prompt = _META_L2_PROMPT.format(child_summaries=child_text)
                else:
                    prompt = _META_L1_PROMPT.format(child_summaries=child_text)
            else:
                member_lines = []
                for node_id in (comm.member_concept_ids or [])[:30]:
                    member_lines.append(_describe_metadata_member(node_id, obj_map, auto_map))
                if not member_lines:
                    continue
                members_text = "\n".join(f"- {line}" for line in member_lines)
                prompt = _META_L0_PROMPT.format(members_text=members_text)

            try:
                result = llm_call(
                    prompt=prompt,
                    max_tokens=300,
                    tier="lite",
                    operation="community_summarization",
                )
                summary = result.text.strip()
                comm.summary = summary
                comm.label = _extract_label_from_summary(summary, comm.label or "")[:512]
                comm_summary_cache[comm.id] = summary
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
    """Generate LLM summaries + embeddings for all document communities in an org.

    Leaf communities get concept+excerpt-based summaries. Parent communities
    get summaries built from their children's summaries.
    """
    from app.models.document import DocumentChunk
    from app.models.knowledge import Concept

    comms_q = await db.execute(
        select(Community).where(
            Community.org_id == org_id,
            Community.source == "document",
            Community.summary.is_(None),
        ).order_by(Community.level.desc())
    )
    communities = comms_q.scalars().all()
    if not communities:
        return 0

    client = get_embedding_provider()
    summarized = 0
    comm_summary_cache: dict[UUID, str] = {}

    by_level: dict[int, list[Community]] = {}
    for c in communities:
        by_level.setdefault(c.level, []).append(c)

    for level in sorted(by_level.keys(), reverse=True):
        for comm in by_level[level]:
            children_q = await db.execute(
                select(Community).where(Community.parent_id == comm.id)
            )
            children = children_q.scalars().all()
            child_summaries = [
                comm_summary_cache.get(c.id, c.summary or "")
                for c in children if c.id in comm_summary_cache or c.summary
            ]

            if child_summaries:
                child_text = "\n\n".join(f"- {s}" for s in child_summaries)
                prompt = _DOC_L1_PROMPT.format(child_summaries=child_text)
            else:
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

                excerpts_section = ""
                if excerpts:
                    excerpts_section = f"\n## Representative Excerpts\n{excerpts[:2000]}"

                prompt = _DOC_SUMMARY_PROMPT.format(
                    concepts=concepts_str,
                    excerpts_section=excerpts_section,
                )

            try:
                result = llm_call(
                    prompt=prompt,
                    max_tokens=300,
                    tier="lite",
                    operation="community_summarization",
                )
                summary = result.text.strip()
                comm.summary = summary
                comm.label = _extract_label_from_summary(summary, comm.label or "")[:512]
                comm_summary_cache[comm.id] = summary
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
