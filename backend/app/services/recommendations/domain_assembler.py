"""Phase 1: Domain context assembly from discovery data.

Pure Python + SQL. No LLM calls. Assembles a structured context document
per domain for the agent opportunity analysis in Phase 2.
"""
from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess

logger = logging.getLogger(__name__)

MAX_STEPS_PER_PROCESS = 8


def _extract_actors(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("role") or str(item)
                out.append(str(name))
        return out
    return [str(raw)]


def _extract_touchpoint_strings(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                obj = item.get("object", "")
                field = item.get("field", "")
                if obj and field:
                    out.append(f"{obj}.{field}")
                elif obj:
                    out.append(str(obj))
                else:
                    out.append(json.dumps(item, default=str))
            else:
                out.append(str(item))
        return out
    return [str(raw)]


def build_actor_roster(processes: list[dict]) -> dict[str, list[str]]:
    roster: dict[str, list[str]] = defaultdict(list)
    for proc in processes:
        proc_name = proc.get("name", "?")
        for actor in _extract_actors(proc.get("actors")):
            roster[actor].append(proc_name)
        for step in proc.get("steps", []):
            step_name = step.get("name", "?")
            for actor in _extract_actors(step.get("actors")):
                roster[actor].append(f"{proc_name} > {step_name}")
    return {k: v for k, v in roster.items() if v}


def build_touchpoint_inventory(processes: list[dict]) -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = defaultdict(list)
    for proc in processes:
        for tp in _extract_touchpoint_strings(proc.get("system_touchpoints")):
            if "." in tp:
                obj, field = tp.split(".", 1)
                if field not in inventory[obj]:
                    inventory[obj].append(field)
            else:
                if tp not in inventory:
                    inventory[tp] = []
        for step in proc.get("steps", []):
            for tp in _extract_touchpoint_strings(step.get("system_touchpoints")):
                if "." in tp:
                    obj, field = tp.split(".", 1)
                    if field not in inventory[obj]:
                        inventory[obj].append(field)
                else:
                    if tp not in inventory:
                        inventory[tp] = []
    return dict(inventory)


def truncate_steps_for_token_budget(
    steps: list[dict], max_steps: int = MAX_STEPS_PER_PROCESS
) -> list[dict]:
    if len(steps) <= max_steps:
        return steps
    complexity_order = {"high": 0, "medium": 1, "low": 2, None: 1}
    ranked = sorted(
        steps,
        key=lambda s: complexity_order.get(
            (s.get("complexity_score") or "").lower() or None, 1
        ),
    )
    return ranked[:max_steps]


def _process_to_context(proc: BusinessProcess, children: list[BusinessProcess]) -> dict:
    steps_raw = []
    for child in children:
        steps_raw.append({
            "id": str(child.id),
            "name": child.name,
            "level": child.level,
            "actors": list(child.actors) if child.actors else [],
            "decision_logic": list(child.decision_logic) if child.decision_logic else [],
            "trigger_conditions": list(child.trigger_conditions) if child.trigger_conditions else [],
            "system_touchpoints": list(child.system_touchpoints) if child.system_touchpoints else [],
            "failure_modes": list(child.failure_modes) if child.failure_modes else [],
            "estimated_duration": child.estimated_duration,
            "estimated_frequency": child.estimated_frequency,
            "sequencing": dict(child.sequencing) if child.sequencing else {},
            "value_classification": child.value_classification,
            "complexity_score": child.complexity_score,
        })

    steps_truncated = truncate_steps_for_token_budget(steps_raw)

    return {
        "id": str(proc.id),
        "name": proc.name,
        "level": proc.level,
        "description": proc.description,
        "narrative": proc.narrative,
        "actors": list(proc.actors) if proc.actors else [],
        "trigger_conditions": list(proc.trigger_conditions) if proc.trigger_conditions else [],
        "decision_logic": list(proc.decision_logic) if proc.decision_logic else [],
        "system_touchpoints": list(proc.system_touchpoints) if proc.system_touchpoints else [],
        "failure_modes": list(proc.failure_modes) if proc.failure_modes else [],
        "value_classification": proc.value_classification,
        "complexity_score": proc.complexity_score,
        "automation_potential": proc.automation_potential,
        "estimated_duration": proc.estimated_duration,
        "estimated_frequency": proc.estimated_frequency,
        "steps": steps_truncated,
    }


def serialize_domain_context(
    domain: dict,
    processes: list[dict],
    handoffs: list[dict],
) -> dict:
    return {
        "domain": domain,
        "processes": processes,
        "handoffs": handoffs,
        "actor_roster": build_actor_roster(processes),
        "system_touchpoints_summary": build_touchpoint_inventory(processes),
    }


async def assemble_domain_contexts(
    org_id: UUID, db: AsyncSession
) -> list[dict]:
    run_res = await db.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.org_id == org_id, DiscoveryRun.status == "completed")
        .order_by(DiscoveryRun.completed_at.desc().nulls_last())
        .limit(1)
    )
    run = run_res.scalar_one_or_none()
    if run is None:
        return []

    all_procs_res = await db.execute(
        select(BusinessProcess)
        .where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run.id,
        )
        .options(selectinload(BusinessProcess.parent))
    )
    all_procs = all_procs_res.scalars().unique().all()

    domains = [p for p in all_procs if p.level == "domain"]
    procs_by_parent: dict[UUID, list[BusinessProcess]] = defaultdict(list)
    for p in all_procs:
        if p.parent_id is not None:
            procs_by_parent[p.parent_id].append(p)

    handoff_res = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == run.id,
        )
    )
    all_handoffs = handoff_res.scalars().all()

    domain_proc_ids: dict[UUID, set[UUID]] = {}

    contexts: list[dict] = []
    for domain in domains:
        domain_dict = {
            "id": str(domain.id),
            "name": domain.name,
            "description": domain.description,
            "narrative": domain.narrative,
        }

        child_procs = procs_by_parent.get(domain.id, [])
        process_level = [p for p in child_procs if p.level in ("process", "subprocess")]

        proc_contexts = []
        all_ids_in_domain: set[UUID] = {domain.id}
        for proc in process_level:
            all_ids_in_domain.add(proc.id)
            children = procs_by_parent.get(proc.id, [])
            for c in children:
                all_ids_in_domain.add(c.id)
            proc_contexts.append(_process_to_context(proc, children))

        random.shuffle(proc_contexts)

        domain_proc_ids[domain.id] = all_ids_in_domain

        domain_handoffs = []
        for h in all_handoffs:
            if h.source_process_id in all_ids_in_domain or h.target_process_id in all_ids_in_domain:
                src_name = next(
                    (p.name for p in all_procs if p.id == h.source_process_id), str(h.source_process_id)
                )
                tgt_name = next(
                    (p.name for p in all_procs if p.id == h.target_process_id), str(h.target_process_id)
                )
                domain_handoffs.append({
                    "source_process": src_name,
                    "target_process": tgt_name,
                    "handoff_type": h.handoff_type,
                    "is_gap": h.is_gap,
                    "description": h.description,
                })

        ctx = serialize_domain_context(domain_dict, proc_contexts, domain_handoffs)
        ctx["_discovery_run_id"] = str(run.id)
        ctx["_domain_db_id"] = str(domain.id)
        contexts.append(ctx)

    return contexts
