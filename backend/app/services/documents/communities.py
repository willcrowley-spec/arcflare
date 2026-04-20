"""Leiden community detection over concept co-occurrence graphs."""

import logging
from uuid import UUID

import igraph
import leidenalg
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    ChunkCommunity,
    Community,
    Concept,
    ConceptCooccurrence,
)

logger = logging.getLogger(__name__)

LEIDEN_RESOLUTION = 1.0
LEIDEN_SEED = 42
LEIDEN_MAX_COMM_SIZE = 10
LEIDEN_N_ITERATIONS = -1
MIN_COMMUNITY_SIZE = 2


async def detect_communities(org_id: UUID, db: AsyncSession) -> list[UUID]:
    """Run Leiden community detection on an org's concept graph.

    Replaces all existing communities for the org.
    Returns list of new community IDs.
    """
    async def _clear_existing() -> None:
        doc_comm_ids = select(Community.id).where(
            Community.org_id == org_id, Community.source == "document"
        )
        await db.execute(delete(ChunkCommunity).where(
            ChunkCommunity.community_id.in_(doc_comm_ids)
        ))
        await db.execute(delete(Community).where(
            Community.org_id == org_id, Community.source == "document"
        ))
        await db.flush()

    concepts_q = await db.execute(
        select(Concept).where(Concept.org_id == org_id)
    )
    concepts = concepts_q.scalars().all()
    if len(concepts) < 2:
        await _clear_existing()
        return []

    concept_idx = {c.id: i for i, c in enumerate(concepts)}
    idx_to_concept = {i: c for c, i in concept_idx.items()}

    edges_q = await db.execute(
        select(ConceptCooccurrence).where(
            ConceptCooccurrence.org_id == org_id,
            ConceptCooccurrence.raw_weight >= 1,
        )
    )
    edges = edges_q.scalars().all()

    g = igraph.Graph(n=len(concepts), directed=False)
    edge_list = []
    weights = []
    for e in edges:
        a_idx = concept_idx.get(e.concept_a_id)
        b_idx = concept_idx.get(e.concept_b_id)
        if a_idx is not None and b_idx is not None:
            edge_list.append((a_idx, b_idx))
            weights.append(e.pmi_weight if e.pmi_weight and e.pmi_weight > 0 else 1.0)

    if not edge_list:
        await _clear_existing()
        return []

    g.add_edges(edge_list)
    g.es["weight"] = weights

    partition = leidenalg.find_partition(
        g,
        leidenalg.RBConfigurationVertexPartition,
        weights=weights,
        resolution_parameter=LEIDEN_RESOLUTION,
        n_iterations=LEIDEN_N_ITERATIONS,
        seed=LEIDEN_SEED,
        max_comm_size=LEIDEN_MAX_COMM_SIZE,
    )

    await _clear_existing()

    concept_names = {c.id: c.display_name or c.name for c in concepts}
    concept_freqs = {c.id: c.frequency for c in concepts}

    new_community_ids = []
    for comm_idx, members in enumerate(partition):
        if len(members) < MIN_COMMUNITY_SIZE:
            continue

        member_concept_ids = [idx_to_concept[m] for m in members]
        sorted_by_freq = sorted(
            member_concept_ids, key=lambda cid: concept_freqs.get(cid, 0), reverse=True
        )
        top_names = [concept_names.get(cid, "?") for cid in sorted_by_freq[:5]]
        label = ", ".join(top_names)

        community = Community(
            org_id=org_id,
            level=0,
            source="document",
            label=label,
            member_concept_ids=[str(cid) for cid in member_concept_ids],
            metadata_json={
                "concept_count": len(member_concept_ids),
                "top_concepts": top_names,
            },
        )
        db.add(community)
        await db.flush()
        new_community_ids.append(community.id)

    await db.flush()
    return new_community_ids


async def link_chunks_to_communities(org_id: UUID, db: AsyncSession) -> None:
    """Link document chunks to communities based on concept membership."""
    communities_q = await db.execute(
        select(Community).where(
            Community.org_id == org_id, Community.source == "document"
        )
    )
    communities = communities_q.scalars().all()

    concept_to_community: dict[str, UUID] = {}
    for comm in communities:
        for cid in comm.member_concept_ids:
            concept_to_community[cid] = comm.id

    from app.models.document import Document, DocumentChunk
    chunks_q = await db.execute(
        select(DocumentChunk).join(Document).where(
            Document.org_id == org_id,
            DocumentChunk.concept_ids != None,
        )
    )
    chunks = chunks_q.scalars().all()

    for chunk in chunks:
        if not chunk.concept_ids:
            continue
        seen_communities: set[UUID] = set()
        for cid in chunk.concept_ids:
            comm_id = concept_to_community.get(str(cid))
            if comm_id and comm_id not in seen_communities:
                seen_communities.add(comm_id)
                db.add(ChunkCommunity(chunk_id=chunk.id, community_id=comm_id))

    await db.flush()
