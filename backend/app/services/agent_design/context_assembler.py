from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataObject
from app.models.process import BusinessProcess
from app.models.recommendation import Recommendation


async def assemble_generation_context(
    db: AsyncSession,
    *,
    org_id: UUID,
    recommendation: Recommendation,
) -> dict:
    """Collect the bounded, org-scoped context used by Generate Agent."""
    process_ids = {str(pid) for pid in (recommendation.linked_process_ids or []) if pid}
    step_ids = {str(sid) for sid in (recommendation.linked_step_ids or []) if sid}
    if recommendation.domain_id:
        process_ids.add(str(recommendation.domain_id))

    processes: list[BusinessProcess] = []
    if process_ids or step_ids:
        ids = {UUID(pid) for pid in process_ids | step_ids}
        q = await db.execute(
            select(BusinessProcess).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.id.in_(ids),
            )
        )
        processes = list(q.scalars().all())

    objects_q = await db.execute(
        select(MetadataObject)
        .where(MetadataObject.org_id == org_id)
        .order_by(MetadataObject.api_name)
        .limit(250)
    )
    objects = list(objects_q.scalars().all())

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
        "processes": [
            {
                "id": str(p.id),
                "name": p.name,
                "level": p.level,
                "description": p.description,
                "actors": p.actors or [],
                "system_touchpoints": p.system_touchpoints or [],
                "decision_logic": p.decision_logic or [],
                "failure_modes": p.failure_modes or [],
                "value_classification": p.value_classification,
                "automation_potential": p.automation_potential,
                "confidence_score": p.confidence_score,
                "evidence_sources": p.evidence_sources or [],
            }
            for p in processes
        ],
        "salesforce_metadata": {
            "objects": [
                {
                    "api_name": o.api_name,
                    "label": o.label,
                    "classification": o.classification,
                    "record_count": int(o.record_count or 0),
                    "field_count": int(o.field_count or 0),
                }
                for o in objects
            ],
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
