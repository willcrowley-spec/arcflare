"""Graph operations for mined processes."""

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import ProcessHandoff
from app.models.process import BusinessProcess, ProcessEdge, ProcessNode

logger = logging.getLogger(__name__)

_COL_SPACING = 320
_ROW_SPACING = 160


async def build_process_graph(process_id: UUID, db: AsyncSession) -> dict:
    """Return nodes and edges for a process as a JSON-serializable structure.

    For domains: auto-generates a graph from child processes + handoffs if no
    explicit ProcessNode rows exist yet.
    """
    proc = await db.get(BusinessProcess, process_id)
    if proc is None:
        raise ValueError("Process not found")

    nodes = (
        await db.execute(select(ProcessNode).where(ProcessNode.process_id == process_id))
    ).scalars().all()
    edges = (
        await db.execute(select(ProcessEdge).where(ProcessEdge.process_id == process_id))
    ).scalars().all()

    if not nodes:
        return await _build_hierarchy_graph(proc, db)

    return _serialize_graph(proc, nodes, edges)


def _serialize_graph(proc: BusinessProcess, nodes: list, edges: list) -> dict:
    return {
        "process": {"id": str(proc.id), "name": proc.name},
        "nodes": [
            {
                "id": str(n.id),
                "type": n.node_type,
                "label": n.label,
                "subtitle": n.subtitle,
                "position": {"x": n.position_x, "y": n.position_y},
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": str(e.id),
                "source": str(e.source_node_id),
                "target": str(e.target_node_id),
                "label": (e.relationship_label or "handoff").split(":")[0].strip()[:30],
                "description": e.relationship_label,
            }
            for e in edges
        ],
    }


async def _build_hierarchy_graph(proc: BusinessProcess, db: AsyncSession) -> dict:
    """Generate a virtual graph from the process hierarchy (no persistence).

    Returns children as nodes laid out in a grid, with handoffs as edges.
    """
    children_q = await db.execute(
        select(BusinessProcess)
        .where(BusinessProcess.parent_id == proc.id)
        .order_by(BusinessProcess.name)
    )
    children = children_q.scalars().all()

    if not children:
        return {"process": {"id": str(proc.id), "name": proc.name}, "nodes": [], "edges": []}

    cols = max(3, int(len(children) ** 0.5) + 1)
    nodes = []
    for i, child in enumerate(children):
        col = i % cols
        row = i // cols
        nodes.append({
            "id": str(child.id),
            "type": child.level or "process",
            "label": child.name,
            "subtitle": (child.description or "")[:80],
            "position": {"x": col * _COL_SPACING, "y": row * _ROW_SPACING},
        })

    child_ids = {c.id for c in children}
    handoffs_q = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.source_process_id.in_(child_ids),
            ProcessHandoff.target_process_id.in_(child_ids),
        )
    )
    handoffs = handoffs_q.scalars().all()

    edges = []
    for ho in handoffs:
        edges.append({
            "id": str(ho.id),
            "source": str(ho.source_process_id),
            "target": str(ho.target_process_id),
            "label": ho.handoff_type or "handoff",
            "description": ho.description,
            "is_gap": ho.is_gap,
        })

    return {"process": {"id": str(proc.id), "name": proc.name}, "nodes": nodes, "edges": edges}


async def generate_graphs_for_run(
    org_id: UUID,
    run_id: UUID,
    db: AsyncSession,
) -> int:
    """Create persisted ProcessNode/ProcessEdge rows for all domains in a discovery run.

    Each domain gets a graph where its direct child processes are nodes,
    and any handoffs between them become edges.  Returns total node count.
    """
    domains_q = await db.execute(
        select(BusinessProcess).where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run_id,
            BusinessProcess.level == "domain",
        )
    )
    domains = domains_q.scalars().all()
    total_nodes = 0

    for domain in domains:
        await db.execute(
            delete(ProcessEdge).where(ProcessEdge.process_id == domain.id)
        )
        await db.execute(
            delete(ProcessNode).where(ProcessNode.process_id == domain.id)
        )

        children_q = await db.execute(
            select(BusinessProcess)
            .where(BusinessProcess.parent_id == domain.id)
            .order_by(BusinessProcess.name)
        )
        children = children_q.scalars().all()
        if not children:
            continue

        cols = max(3, int(len(children) ** 0.5) + 1)
        child_to_node: dict[UUID, ProcessNode] = {}

        for i, child in enumerate(children):
            col = i % cols
            row = i // cols
            node = ProcessNode(
                process_id=domain.id,
                node_type=child.level or "process",
                label=child.name,
                subtitle=(child.description or "")[:120],
                position_x=col * _COL_SPACING,
                position_y=row * _ROW_SPACING,
                metadata_json={"child_process_id": str(child.id)},
            )
            db.add(node)
            await db.flush()
            child_to_node[child.id] = node
            total_nodes += 1

        child_ids = set(child_to_node.keys())
        handoffs_q = await db.execute(
            select(ProcessHandoff).where(
                ProcessHandoff.source_process_id.in_(child_ids),
                ProcessHandoff.target_process_id.in_(child_ids),
            )
        )
        seen_edges: set[tuple[UUID, UUID]] = set()
        for ho in handoffs_q.scalars().all():
            src_node = child_to_node.get(ho.source_process_id)
            tgt_node = child_to_node.get(ho.target_process_id)
            if src_node and tgt_node:
                edge_key = (src_node.id, tgt_node.id)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                db.add(ProcessEdge(
                    process_id=domain.id,
                    source_node_id=src_node.id,
                    target_node_id=tgt_node.id,
                    relationship_label=ho.handoff_type or "handoff",
                    metadata_json={
                        "handoff_id": str(ho.id),
                        "description": ho.description,
                        "is_gap": ho.is_gap,
                    },
                ))

        await db.flush()

    logger.info(
        "graph_generation_complete org_id=%s run_id=%s domains=%d nodes=%d",
        org_id, run_id, len(domains), total_nodes,
    )
    return total_nodes


async def update_node_positions(
    process_id: UUID,
    positions: dict[str, tuple[float, float]],
    db: AsyncSession,
) -> int:
    """Bulk-update node coordinates keyed by node id string."""
    updated = 0
    for nid, (x, y) in positions.items():
        node = await db.get(ProcessNode, UUID(nid))
        if node is None or node.process_id != process_id:
            continue
        node.position_x = float(x)
        node.position_y = float(y)
        updated += 1
    await db.flush()
    return updated
