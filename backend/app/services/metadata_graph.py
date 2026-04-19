"""Build metadata dependency edges and run graph-derived community detection."""
from __future__ import annotations

import logging
from uuid import UUID

import igraph
import leidenalg
import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Community
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataDependency,
    MetadataObject,
)

logger = logging.getLogger(__name__)

YIELD_PER = 200
METADATA_LEIDEN_SEED = 42
METADATA_LEIDEN_N_ITERATIONS = -1
METADATA_CPM_RESOLUTION = 0.05
METADATA_MIN_COMMUNITY_SIZE = 2


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict] = []
    for e in edges:
        key = (
            e["source_type"],
            e["source_api_name"],
            e["relationship_type"],
            e["target_type"],
            e["target_api_name"],
        )
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _as_str_list(val: object) -> list[str]:
    if not isinstance(val, list):
        return []
    return [x.strip() for x in val if isinstance(x, str) and x.strip()]


def _filter_edge_for_objects(e: dict, valid_objects: set[str]) -> bool:
    if e["target_type"] != "object":
        return True
    return e["target_api_name"] in valid_objects


def _edges_from_flow(api: str, meta: dict) -> list[dict]:
    edges: list[dict] = []
    trig = meta.get("trigger_object")
    if isinstance(trig, str) and trig:
        edges.append(
            {
                "source_type": "flow",
                "source_api_name": api,
                "relationship_type": "triggers_on",
                "target_type": "object",
                "target_api_name": trig,
                "metadata_json": {},
            }
        )
    elems = meta.get("elements") or {}
    for rl in elems.get("record_lookups") or []:
        obj = rl.get("object") if isinstance(rl, dict) else None
        if obj:
            edges.append(
                {
                    "source_type": "flow",
                    "source_api_name": api,
                    "relationship_type": "reads",
                    "target_type": "object",
                    "target_api_name": obj,
                    "metadata_json": {},
                }
            )
    for key in ("record_creates", "record_updates", "record_deletes"):
        for el in elems.get(key) or []:
            obj = el.get("object") if isinstance(el, dict) else None
            if obj:
                edges.append(
                    {
                        "source_type": "flow",
                        "source_api_name": api,
                        "relationship_type": "writes",
                        "target_type": "object",
                        "target_api_name": obj,
                        "metadata_json": {},
                    }
                )
    for sf in elems.get("subflows") or []:
        name = sf.get("flow_name") if isinstance(sf, dict) else None
        if name:
            edges.append(
                {
                    "source_type": "flow",
                    "source_api_name": api,
                    "relationship_type": "calls_subflow",
                    "target_type": "flow",
                    "target_api_name": name,
                    "metadata_json": {},
                }
            )
    for ac in elems.get("action_calls") or []:
        if not isinstance(ac, dict):
            continue
        if ac.get("action_type") == "apex":
            edges.append(
                {
                    "source_type": "flow",
                    "source_api_name": api,
                    "relationship_type": "invokes_apex",
                    "target_type": "apex_class",
                    "target_api_name": ac.get("action_name", ""),
                    "metadata_json": {},
                }
            )
        elif ac.get("action_type") == "emailAlert":
            edges.append(
                {
                    "source_type": "flow",
                    "source_api_name": api,
                    "relationship_type": "sends_email",
                    "target_type": "email_template",
                    "target_api_name": ac.get("action_name", ""),
                    "metadata_json": {},
                }
            )
    return edges


def _edges_from_apex_class(api: str, meta: dict) -> list[dict]:
    edges: list[dict] = []
    for obj in _as_str_list(meta.get("soql_objects")):
        edges.append(
            {
                "source_type": "apex_class",
                "source_api_name": api,
                "relationship_type": "reads",
                "target_type": "object",
                "target_api_name": obj,
                "metadata_json": {},
            }
        )
    for obj in _as_str_list(meta.get("dml_objects")):
        edges.append(
            {
                "source_type": "apex_class",
                "source_api_name": api,
                "relationship_type": "writes",
                "target_type": "object",
                "target_api_name": obj,
                "metadata_json": {},
            }
        )
    return edges


def _edges_from_object_relationships(api: str, rels: list) -> list[dict]:
    edges: list[dict] = []
    for r in rels:
        if not isinstance(r, dict):
            continue
        ref = r.get("referenceTo") or r.get("references_to") or []
        rtype = r.get("relationshipType", r.get("type", "lookup")).lower()
        rel = "master_detail" if "master" in rtype else "lookup"
        targets = ref if isinstance(ref, list) else [ref]
        for t in targets:
            if isinstance(t, str) and t:
                edges.append(
                    {
                        "source_type": "object",
                        "source_api_name": api,
                        "relationship_type": rel,
                        "target_type": "object",
                        "target_api_name": t,
                        "metadata_json": {},
                    }
                )
    return edges


async def build_dependency_graph(connection_id: UUID, org_id: UUID, db: AsyncSession) -> int:
    await db.execute(delete(MetadataDependency).where(MetadataDependency.connection_id == connection_id))
    await db.flush()

    valid_objects: set[str] = set()
    res = await db.execute(select(MetadataObject.api_name).where(MetadataObject.connection_id == connection_id))
    valid_objects.update(r[0] for r in res.all())

    all_edges: list[dict] = []

    auto_stmt = select(MetadataAutomation).where(MetadataAutomation.connection_id == connection_id).execution_options(
        yield_per=YIELD_PER
    )
    stream = await db.stream_scalars(auto_stmt)
    async for part in stream.partitions(YIELD_PER):
        for auto in part:
            meta = auto.metadata_json or {}
            t = auto.automation_type
            if t == "flow":
                all_edges.extend(_edges_from_flow(auto.api_name, meta))
            elif t in ("trigger", "apex_trigger"):
                obj = meta.get("trigger_object") or auto.related_object
                if obj:
                    all_edges.append(
                        {
                            "source_type": "apex_trigger",
                            "source_api_name": auto.api_name,
                            "relationship_type": "triggers_on",
                            "target_type": "object",
                            "target_api_name": obj,
                            "metadata_json": {},
                        }
                    )
            elif t == "validation_rule" and auto.related_object:
                all_edges.append(
                    {
                        "source_type": "validation_rule",
                        "source_api_name": auto.api_name,
                        "relationship_type": "validates",
                        "target_type": "object",
                        "target_api_name": auto.related_object,
                        "metadata_json": {},
                    }
                )
            elif t == "workflow_rule" and auto.related_object:
                all_edges.append(
                    {
                        "source_type": "workflow_rule",
                        "source_api_name": auto.api_name,
                        "relationship_type": "triggers_on",
                        "target_type": "object",
                        "target_api_name": auto.related_object,
                        "metadata_json": {},
                    }
                )
            elif t == "approval_process" and auto.related_object:
                all_edges.append(
                    {
                        "source_type": "approval_process",
                        "source_api_name": auto.api_name,
                        "relationship_type": "triggers_on",
                        "target_type": "object",
                        "target_api_name": auto.related_object,
                        "metadata_json": {},
                    }
                )

    comp_stmt = select(MetadataComponent).where(
        MetadataComponent.connection_id == connection_id,
        MetadataComponent.component_category == "apex_class",
    ).execution_options(yield_per=YIELD_PER)
    comp_stream = await db.stream_scalars(comp_stmt)
    async for part in comp_stream.partitions(YIELD_PER):
        for comp in part:
            all_edges.extend(_edges_from_apex_class(comp.api_name, comp.metadata_json or {}))

    obj_stmt = select(MetadataObject).where(MetadataObject.connection_id == connection_id).execution_options(
        yield_per=YIELD_PER
    )
    obj_stream = await db.stream_scalars(obj_stmt)
    async for part in obj_stream.partitions(YIELD_PER):
        for obj in part:
            rels = (obj.metadata_json or {}).get("relationships") or []
            all_edges.extend(_edges_from_object_relationships(obj.api_name, rels))

    filtered = [e for e in _dedupe_edges(all_edges) if _filter_edge_for_objects(e, valid_objects)]
    if not filtered:
        return 0

    for i in range(0, len(filtered), 500):
        rows = [{"org_id": org_id, "connection_id": connection_id, **e} for e in filtered[i : i + 500]]
        await db.execute(pg_insert(MetadataDependency), rows)
    await db.flush()
    logger.info("build_dependency_graph connection=%s edges=%d", connection_id, len(filtered))
    return len(filtered)


def _node_id(t: str, name: str) -> str:
    return f"{t}:{name}"


async def detect_metadata_communities(
    connection_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> int:
    dep_stmt = select(
        MetadataDependency.source_type,
        MetadataDependency.source_api_name,
        MetadataDependency.target_type,
        MetadataDependency.target_api_name,
    ).where(MetadataDependency.connection_id == connection_id)
    res = await db.execute(dep_stmt)

    nodes: set[str] = set()
    edge_pairs: list[tuple[str, str]] = []
    for st, sn, tt, tn in res.all():
        a, b = _node_id(st, sn), _node_id(tt, tn)
        nodes.add(a)
        nodes.add(b)
        if a != b:
            edge_pairs.append((a, b))

    await db.execute(
        delete(Community).where(
            Community.org_id == org_id,
            sa.cast(Community.metadata_json["source"], sa.String) == "metadata_graph",
        )
    )
    await db.flush()

    if len(nodes) < 2 or not edge_pairs:
        logger.info("detect_metadata_communities_skip connection=%s", connection_id)
        return 0

    index = {n: i for i, n in enumerate(sorted(nodes))}
    rev = {i: n for n, i in index.items()}
    g = igraph.Graph(n=len(index), directed=False)
    g.add_edges([(index[a], index[b]) for a, b in edge_pairs])

    partition = leidenalg.find_partition(
        g,
        leidenalg.CPMVertexPartition,
        resolution_parameter=METADATA_CPM_RESOLUTION,
        n_iterations=METADATA_LEIDEN_N_ITERATIONS,
        seed=METADATA_LEIDEN_SEED,
    )

    created = 0
    for members in partition:
        member_ids = [rev[m] for m in members]
        if len(member_ids) < METADATA_MIN_COMMUNITY_SIZE:
            continue
        top3 = sorted(member_ids, key=lambda x: x.split(":", 1)[1])[:3]
        label = ", ".join(n.split(":", 1)[1] for n in top3)
        db.add(
            Community(
                org_id=org_id,
                level=0,
                label=label[:512],
                member_concept_ids=member_ids,
                metadata_json={
                    "source": "metadata_graph",
                    "connection_id": str(connection_id),
                    "member_count": len(member_ids),
                },
            )
        )
        created += 1
    await db.flush()
    logger.info("detect_metadata_communities connection=%s communities=%d", connection_id, created)
    return created
