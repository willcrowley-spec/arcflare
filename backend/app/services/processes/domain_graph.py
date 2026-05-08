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
        "positions": _normalize_positions(getattr(domain, "domain_map_positions", {}) or {}),
    }


async def _fetch_subtree(
    domain_id: UUID, org_id: UUID, db: AsyncSession
) -> list[dict]:
    """Fetch all descendants of a domain using a recursive CTE."""
    cte_sql = sa_text("""
        WITH RECURSIVE subtree AS (
            SELECT id, name, parent_id, level, status, confidence_score,
                   needs_review, description, actors, artifacts,
                   trigger_conditions, decision_logic, system_touchpoints,
                   success_criteria, failure_modes, value_classification,
                   complexity_score, automation_potential, estimated_duration,
                   estimated_frequency, sequencing, evidence_sources
            FROM business_processes
            WHERE parent_id = :domain_id AND org_id = :org_id
            UNION ALL
            SELECT bp.id, bp.name, bp.parent_id, bp.level, bp.status,
                   bp.confidence_score, bp.needs_review, bp.description,
                   bp.actors, bp.artifacts, bp.trigger_conditions,
                   bp.decision_logic, bp.system_touchpoints, bp.success_criteria,
                   bp.failure_modes, bp.value_classification, bp.complexity_score,
                   bp.automation_potential, bp.estimated_duration,
                   bp.estimated_frequency, bp.sequencing, bp.evidence_sources
            FROM business_processes bp
            INNER JOIN subtree s ON bp.parent_id = s.id
        )
        SELECT id, name, parent_id, level, status, confidence_score,
               needs_review, description, actors, artifacts,
               trigger_conditions, decision_logic, system_touchpoints,
               success_criteria, failure_modes, value_classification,
               complexity_score, automation_potential, estimated_duration,
               estimated_frequency, sequencing, evidence_sources
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
                "actors": _list_field(c.get("actors")),
                "artifacts": _list_field(c.get("artifacts")),
                "trigger_conditions": _list_field(c.get("trigger_conditions")),
                "decision_logic": _list_field(c.get("decision_logic")),
                "system_touchpoints": _list_field(c.get("system_touchpoints")),
                "success_criteria": _list_field(c.get("success_criteria")),
                "failure_modes": _list_field(c.get("failure_modes")),
                "value_classification": c.get("value_classification"),
                "complexity_score": c.get("complexity_score"),
                "automation_potential": c.get("automation_potential"),
                "estimated_duration": c.get("estimated_duration"),
                "estimated_frequency": c.get("estimated_frequency"),
                "sequencing": _dict_field(c.get("sequencing")),
                "evidence_sources": _list_field(c.get("evidence_sources")),
                "is_leaf": is_leaf,
                "leaf_count": leaf_count,
                "children": kids,
            })
        return result

    return build(domain_id)


async def _fetch_edges(descendants: list[dict], db: AsyncSession) -> list[dict]:
    """Fetch normalized sequence and handoff edges between processes in the subtree."""
    all_ids = {d["id"] for d in descendants}
    if not all_ids:
        return []
    all_id_strings = {str(process_id) for process_id in all_ids}
    edges_by_key: dict[tuple[str, str, str], dict] = {}

    for edge in _sequencing_edges(descendants, all_id_strings):
        edges_by_key[(edge["source_id"], edge["target_id"], edge["kind"])] = edge

    q = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.source_process_id.in_(all_ids),
            ProcessHandoff.target_process_id.in_(all_ids),
        )
    )
    handoffs = q.scalars().all()

    for h in handoffs:
        edge = _handoff_edge(h)
        edges_by_key[(edge["source_id"], edge["target_id"], edge["kind"])] = edge

    return sorted(
        edges_by_key.values(),
        key=lambda edge: (edge["source_id"], edge["target_id"], edge["kind"], edge["id"]),
    )


def _sequencing_edges(descendants: list[dict], all_id_strings: set[str]) -> list[dict]:
    """Project lightweight intra-process sequencing data into normalized graph edges."""
    edges = []
    for row in descendants:
        sequencing = _dict_field(row.get("sequencing"))
        successors = sequencing.get("successors") or []
        if not isinstance(successors, list):
            continue

        source_id = str(row["id"])
        for index, successor in enumerate(successors):
            if not isinstance(successor, dict):
                continue
            target_id = successor.get("step_id") or successor.get("process_id") or successor.get("id")
            if target_id is None or str(target_id) not in all_id_strings:
                continue
            label = successor.get("condition") or successor.get("label") or "sequence"
            edges.append({
                "id": f"sequence-{source_id}-{target_id}-{index}",
                "source_id": source_id,
                "target_id": str(target_id),
                "label": label,
                "description": successor.get("description"),
                "kind": "sequence",
                "confidence_score": row.get("confidence_score"),
                "is_gap": False,
                "gap_status": None,
                "needs_review": False,
                "evidence_sources": [],
                "data_transferred": [],
                "transfer_mechanism": successor.get("transfer_mechanism"),
            })
    return edges


def _handoff_edge(handoff: ProcessHandoff) -> dict:
    metadata = _dict_field(getattr(handoff, "metadata_json", {}))
    return {
        "id": str(handoff.id),
        "source_id": str(handoff.source_process_id),
        "target_id": str(handoff.target_process_id),
        "label": handoff.handoff_type or "handoff",
        "description": handoff.description,
        "kind": "handoff",
        "confidence_score": getattr(handoff, "confidence_score", None),
        "is_gap": bool(getattr(handoff, "is_gap", False)),
        "gap_status": getattr(handoff, "gap_status", None),
        "needs_review": bool(getattr(handoff, "needs_review", False)),
        "evidence_sources": _list_field(getattr(handoff, "evidence_sources", [])),
        "data_transferred": _list_field(metadata.get("data_transferred")),
        "transfer_mechanism": metadata.get("transfer_mechanism"),
    }


def _normalize_positions(raw_positions: dict) -> dict[str, dict[str, float]]:
    positions: dict[str, dict[str, float]] = {}
    for process_id, position in raw_positions.items():
        if not isinstance(position, dict):
            continue
        x = position.get("x")
        y = position.get("y")
        if isinstance(x, int | float) and isinstance(y, int | float):
            positions[str(process_id)] = {"x": float(x), "y": float(y)}
    return positions


def _list_field(value) -> list:
    return value if isinstance(value, list) else []


def _dict_field(value) -> dict:
    return value if isinstance(value, dict) else {}
