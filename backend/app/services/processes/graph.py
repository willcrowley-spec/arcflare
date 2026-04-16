"""Graph operations for mined processes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.process import BusinessProcess, ProcessEdge, ProcessNode


async def build_process_graph(process_id: UUID, db: AsyncSession) -> dict:
    """Return nodes and edges for a process as a JSON-serializable structure."""
    proc = await db.get(BusinessProcess, process_id)
    if proc is None:
        raise ValueError("Process not found")
    nodes = (
        await db.execute(select(ProcessNode).where(ProcessNode.process_id == process_id))
    ).scalars().all()
    edges = (
        await db.execute(select(ProcessEdge).where(ProcessEdge.process_id == process_id))
    ).scalars().all()
    return {
        "process": {"id": str(proc.id), "name": proc.name},
        "nodes": [
            {
                "id": str(n.id),
                "type": n.node_type,
                "label": n.label,
                "position": {"x": n.position_x, "y": n.position_y},
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": str(e.id),
                "source": str(e.source_node_id),
                "target": str(e.target_node_id),
                "label": e.relationship_label,
            }
            for e in edges
        ],
    }


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
