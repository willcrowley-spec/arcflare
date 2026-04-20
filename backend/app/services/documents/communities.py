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
LEIDEN_MIN_RECURSE_SIZE = 5
MIN_COMMUNITY_SIZE = 2


def _recursive_doc_leiden(
    g: igraph.Graph,
    idx_to_concept: dict[int, UUID],
    members_list: list[list[int]],
    max_cluster_size: int = LEIDEN_MAX_COMM_SIZE,
    min_recurse_size: int = LEIDEN_MIN_RECURSE_SIZE,
    level: int = 0,
) -> list[tuple[int, list[UUID], int | None]]:
    """Recursively partition document communities exceeding max_cluster_size."""
    results: list[tuple[int, list[UUID], int | None]] = []
    for members in members_list:
        concept_ids = [idx_to_concept[m] for m in members]
        if len(members) <= max_cluster_size or len(members) < min_recurse_size:
            results.append((level, concept_ids, None))
        else:
            parent_idx = len(results)
            results.append((level, concept_ids, parent_idx))
            subgraph = g.subgraph(members)
            sub_idx_map = {i: idx_to_concept[members[i]] for i in range(len(members))}
            sub_weights = subgraph.es["weight"] if subgraph.ecount() > 0 else None
            try:
                sub_partition = leidenalg.find_partition(
                    subgraph,
                    leidenalg.RBConfigurationVertexPartition,
                    weights=sub_weights,
                    resolution_parameter=LEIDEN_RESOLUTION * 1.5,
                    n_iterations=LEIDEN_N_ITERATIONS,
                    seed=LEIDEN_SEED,
                )
                child_groups = [list(m) for m in sub_partition if len(m) >= MIN_COMMUNITY_SIZE]
                if len(child_groups) > 1:
                    children = _recursive_doc_leiden(
                        subgraph, sub_idx_map, child_groups,
                        max_cluster_size, min_recurse_size, level + 1,
                    )
                    results.extend(children)
            except Exception:
                logger.warning("recursive_doc_leiden_failed level=%d members=%d", level, len(members))
    return results


async def detect_communities(
    org_id: UUID,
    db: AsyncSession,
    document_id: UUID | None = None,
) -> list[UUID]:
    """Run Leiden community detection on an org's concept graph.

    Leiden operates on the full org graph — individual documents cannot be
    incrementally re-clustered because adding concepts shifts community
    boundaries globally.  When document_id is given, we skip the rebuild
    if the document introduced no new concepts (fast-path optimisation).
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

    if document_id is not None:
        from app.models.document import DocumentChunk
        doc_concepts_q = await db.execute(
            select(DocumentChunk.concept_ids).where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.concept_ids.isnot(None),
            )
        )
        doc_concept_ids = set()
        for row in doc_concepts_q.all():
            doc_concept_ids.update(row[0] or [])
        if not doc_concept_ids:
            logger.info(
                "detect_communities skip: doc %s added no concepts", document_id,
            )
            existing_q = await db.execute(
                select(Community.id).where(
                    Community.org_id == org_id, Community.source == "document"
                )
            )
            return [r[0] for r in existing_q.all()]

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
    )

    await _clear_existing()

    concept_names = {c.id: c.display_name or c.name for c in concepts}
    concept_freqs = {c.id: c.frequency for c in concepts}

    top_level_groups = [list(m) for m in partition if len(m) >= MIN_COMMUNITY_SIZE]
    hierarchy = _recursive_doc_leiden(g, idx_to_concept, top_level_groups)

    new_community_ids: list[UUID] = []
    idx_to_db_id: dict[int, UUID] = {}

    for i, (level, member_concept_ids, parent_placeholder) in enumerate(hierarchy):
        if len(member_concept_ids) < MIN_COMMUNITY_SIZE:
            continue

        sorted_by_freq = sorted(
            member_concept_ids, key=lambda cid: concept_freqs.get(cid, 0), reverse=True
        )
        top_names = [concept_names.get(cid, "?") for cid in sorted_by_freq[:5]]
        label = ", ".join(top_names)

        parent_db_id = None
        if parent_placeholder is not None and parent_placeholder in idx_to_db_id:
            parent_db_id = idx_to_db_id[parent_placeholder]

        community = Community(
            org_id=org_id,
            parent_id=parent_db_id,
            level=level,
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
        idx_to_db_id[i] = community.id
        new_community_ids.append(community.id)

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
