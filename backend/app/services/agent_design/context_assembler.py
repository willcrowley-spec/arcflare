from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataObject
from app.models.process import BusinessProcess
from app.models.recommendation import Recommendation


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _uuid_values(values: set[str]) -> set[UUID]:
    out: set[UUID] = set()
    for value in values:
        try:
            out.add(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def _serialize_process_row(process: BusinessProcess) -> dict:
    return {
        "id": str(process.id),
        "name": process.name,
        "level": process.level,
        "description": process.description,
        "actors": _as_list(process.actors),
        "system_touchpoints": _as_list(process.system_touchpoints),
        "decision_logic": _as_list(process.decision_logic),
        "failure_modes": _as_list(process.failure_modes),
        "value_classification": process.value_classification,
        "automation_potential": process.automation_potential,
        "confidence_score": process.confidence_score,
        "evidence_sources": _as_list(process.evidence_sources),
    }


def _serialize_process_contexts(
    processes: list[BusinessProcess],
    *,
    process_ids: set[str],
    step_ids: set[str],
) -> list[dict]:
    """Serialize process evidence while removing process ids from step evidence."""
    effective_step_ids = {sid for sid in step_ids if sid not in process_ids}
    children_by_parent: dict[str, list[BusinessProcess]] = {}
    for process in processes:
        parent_id = str(process.parent_id) if process.parent_id else ""
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(process)

    rows = []
    for process in processes:
        process_id = str(process.id)
        if process_id not in process_ids:
            continue
        row = _serialize_process_row(process)
        child_rows = []
        for child in children_by_parent.get(process_id, []):
            child_id = str(child.id)
            if effective_step_ids and child_id not in effective_step_ids:
                continue
            child_rows.append(_serialize_process_row(child))
        row["steps"] = child_rows
        rows.append(row)
    return rows


def _serialize_metadata_object(obj: MetadataObject) -> dict:
    return {
        "api_name": obj.api_name,
        "label": obj.label,
        "classification": obj.classification,
        "record_count": int(obj.record_count or 0),
        "field_count": int(obj.field_count or 0),
        "fields": [
            {
                "api_name": field.api_name,
                "label": field.label,
                "field_type": field.field_type,
                "is_required": bool(field.is_required),
            }
            for field in (obj.fields or [])
        ],
    }


async def assemble_generation_context(
    db: AsyncSession,
    *,
    org_id: UUID,
    recommendation: Recommendation,
) -> dict:
    """Collect the bounded, org-scoped context used by Generate Agent."""
    process_ids = {str(pid) for pid in (recommendation.linked_process_ids or []) if pid}
    step_ids = {
        str(sid)
        for sid in (recommendation.linked_step_ids or [])
        if sid and str(sid) not in process_ids
    }
    if recommendation.domain_id:
        process_ids.add(str(recommendation.domain_id))

    processes: list[BusinessProcess] = []
    if process_ids or step_ids:
        process_uuid_ids = _uuid_values(process_ids)
        ids = process_uuid_ids | _uuid_values(step_ids)
        q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                or_(
                    BusinessProcess.id.in_(ids),
                    BusinessProcess.parent_id.in_(process_uuid_ids),
                ),
            )
        )
        processes = list(q.scalars().all())

    objects_q = await db.execute(
        select(MetadataObject)
        .where(MetadataObject.org_id == org_id)
        .options(selectinload(MetadataObject.fields))
        .order_by(MetadataObject.api_name)
    )
    objects = list(objects_q.scalars().unique().all())

    components_q = await db.execute(
        select(MetadataComponent)
        .where(MetadataComponent.org_id == org_id)
        .order_by(MetadataComponent.component_category, MetadataComponent.api_name)
        .limit(250)
    )
    components = list(components_q.scalars().all())

    automation_q = await db.execute(
        select(MetadataAutomation)
        .where(MetadataAutomation.org_id == org_id)
        .order_by(MetadataAutomation.automation_type, MetadataAutomation.api_name)
        .limit(250)
    )
    automations = list(automation_q.scalars().all())

    return {
        "schema_version": "agent_generation_context_v1",
        "recommendation": {
            "id": str(recommendation.id),
            "title": recommendation.title,
            "description": recommendation.description,
            "status": recommendation.status,
            "automation_type": recommendation.automation_type,
            "recommendation_type": recommendation.recommendation_type,
            "arc_score": recommendation.arc_score_json or {},
            "agent_opportunity": recommendation.agent_opportunity_json or {},
            "actions": recommendation.actions_json or [],
            "assumptions": recommendation.assumptions_json or {},
            "scenarios": recommendation.scenarios_json or {},
        },
        "processes": _serialize_process_contexts(
            processes,
            process_ids=process_ids,
            step_ids=step_ids,
        ),
        "salesforce_metadata": {
            "objects": [_serialize_metadata_object(o) for o in objects],
            "components": [
                {
                    "api_name": c.api_name,
                    "category": c.component_category,
                    "label": c.label,
                    "related_object": c.related_object,
                }
                for c in components
            ],
            "automations": [
                {
                    "api_name": a.api_name,
                    "type": a.automation_type,
                    "label": a.label,
                    "related_object": a.related_object,
                    "status": a.status,
                }
                for a in automations
            ],
        },
    }
