"""Build a full recursive domain graph for the compound map view."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import ProcessHandoff
from app.models.process import BusinessProcess


async def get_domain_graph(domain_id: UUID, org_id: UUID, db: AsyncSession) -> dict:
    """Return the full hierarchy + normalized edges for a domain."""
    domain = await db.get(BusinessProcess, domain_id)
    if domain is None or domain.org_id != org_id:
        raise ValueError("Domain not found")
    if domain.level != "domain":
        raise ValueError("Process is not a domain")

    all_descendants = await _fetch_subtree(domain_id, org_id, db)
    hierarchy = _build_tree(domain_id, all_descendants)
    edges = await _fetch_edges(all_descendants, db)

    return {
        "domain": {"id": str(domain.id), "name": domain.name},
        "hierarchy": hierarchy,
        "edges": edges,
    }


async def _fetch_subtree(
    domain_id: UUID, org_id: UUID, db: AsyncSession
) -> list[dict]:
    """Fetch all descendants of a domain using a recursive CTE."""
    cte_sql = sa_text("""
        WITH RECURSIVE subtree AS (
            SELECT id, name, parent_id, level, status, confidence_score,
                   needs_review, description
            FROM business_processes
            WHERE parent_id = :domain_id AND org_id = :org_id
            UNION ALL
            SELECT bp.id, bp.name, bp.parent_id, bp.level, bp.status,
                   bp.confidence_score, bp.needs_review, bp.description
            FROM business_processes bp
            INNER JOIN subtree s ON bp.parent_id = s.id
        )
        SELECT id, name, parent_id, level, status, confidence_score,
               needs_review, description
        FROM subtree
    """)
    result = await db.execute(cte_sql, {"domain_id": str(domain_id), "org_id": str(org_id)})
    rows = result.mappings().all()
    return [dict(r) for r in rows]


def _count_leaves(process_id: UUID, by_parent: dict[UUID | None, list[dict]]) -> int:
    """Count total leaf descendants recursively."""
    children = by_parent.get(process_id, [])
    if not children:
        return 0
    total = 0
    for child in children:
        grandchildren = by_parent.get(child["id"], [])
        if not grandchildren:
            total += 1
        else:
            total += _count_leaves(child["id"], by_parent)
    return total


def _build_tree(domain_id: UUID, descendants: list[dict]) -> list[dict]:
    """Assemble a nested hierarchy from flat descendant rows."""
    by_parent: dict[UUID | None, list[dict]] = {}
    for d in descendants:
        by_parent.setdefault(d["parent_id"], []).append(d)

    def build(parent_id: UUID) -> list[dict]:
        children = by_parent.get(parent_id, [])
        result = []
        for c in children:
            kids = build(c["id"])
            is_leaf = len(kids) == 0
            leaf_count = 0 if is_leaf else _count_leaves(c["id"], by_parent)
            result.append({
                "id": str(c["id"]),
                "name": c["name"],
                "parent_id": str(c["parent_id"]) if c["parent_id"] else None,
                "level": c["level"],
                "status": c["status"],
                "confidence_score": c.get("confidence_score"),
                "needs_review": c.get("needs_review", False),
                "description": c.get("description"),
                "is_leaf": is_leaf,
                "leaf_count": leaf_count,
                "children": kids,
            })
        return result

    return build(domain_id)


async def _fetch_edges(descendants: list[dict], db: AsyncSession) -> list[dict]:
    """Fetch all handoff edges between any processes in the subtree."""
    all_ids = {d["id"] for d in descendants}
    if not all_ids:
        return []

    q = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.source_process_id.in_(all_ids),
            ProcessHandoff.target_process_id.in_(all_ids),
        )
    )
    handoffs = q.scalars().all()

    edges = []
    for h in handoffs:
        edges.append({
            "id": str(h.id),
            "source_id": str(h.source_process_id),
            "target_id": str(h.target_process_id),
            "label": h.handoff_type or "handoff",
            "description": h.description,
            "is_gap": h.is_gap,
        })
    return edges
