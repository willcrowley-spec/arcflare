"""Stage 1 recommendation pipeline: discovered + synthesized candidates."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess

logger = logging.getLogger(__name__)

_RULE_KEYWORDS = ("if", "when", "rule", "formula", "threshold")
_JUDGMENT_KEYWORDS = ("judgment", "assess", "evaluate", "interpret", "ambiguous")
_CONTEXT_TRIGGER_KEYWORDS = ("unstructured", "contextual")


def _jsonb_list_as_texts(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            else:
                out.append(json.dumps(item, default=str))
        return out
    if isinstance(value, str):
        return [value]
    return [json.dumps(value, default=str)]


def classify_automation_type(process: dict) -> str:
    """Classify automation style from decision_logic and trigger_conditions heuristics."""
    raw_dl = process.get("decision_logic")
    raw_tc = process.get("trigger_conditions")
    if isinstance(raw_dl, dict):
        dl_items: list = [raw_dl]
    elif isinstance(raw_dl, list):
        dl_items = raw_dl
    else:
        dl_items = []

    if isinstance(raw_tc, dict):
        tc_items: list = [raw_tc]
    elif isinstance(raw_tc, list):
        tc_items = raw_tc
    else:
        tc_items = []

    dl_text = " ".join(t.lower() for t in _jsonb_list_as_texts(dl_items))
    tc_text = " ".join(t.lower() for t in _jsonb_list_as_texts(tc_items))

    if any(k in dl_text for k in _JUDGMENT_KEYWORDS):
        return "agentic"
    if any(k in tc_text for k in _CONTEXT_TRIGGER_KEYWORDS):
        return "agentic"

    if not dl_items:
        dl_rule_based = True
    else:
        dl_rule_based = all(
            any(k in _jsonb_list_as_texts([item])[0].lower() for k in _RULE_KEYWORDS)
            for item in dl_items
        )

    triggers_bounded = not any(k in tc_text for k in _CONTEXT_TRIGGER_KEYWORDS)

    if dl_rule_based and triggers_bounded:
        return "deterministic"

    return "hybrid"


def _process_to_base_dict(proc: BusinessProcess) -> dict:
    return {
        "id": proc.id,
        "org_id": proc.org_id,
        "name": proc.name,
        "category": proc.category,
        "description": proc.description,
        "status": proc.status,
        "narrative": proc.narrative,
        "level": proc.level,
        "parent_id": proc.parent_id,
        "discovery_run_id": proc.discovery_run_id,
        "actors": list(proc.actors) if proc.actors is not None else [],
        "artifacts": list(proc.artifacts) if proc.artifacts is not None else [],
        "trigger_conditions": list(proc.trigger_conditions)
        if proc.trigger_conditions is not None
        else [],
        "decision_logic": list(proc.decision_logic) if proc.decision_logic is not None else [],
        "system_touchpoints": list(proc.system_touchpoints)
        if proc.system_touchpoints is not None
        else [],
        "success_criteria": list(proc.success_criteria) if proc.success_criteria is not None else [],
        "failure_modes": list(proc.failure_modes) if proc.failure_modes is not None else [],
        "evidence_sources": list(proc.evidence_sources) if proc.evidence_sources is not None else [],
        "value_classification": proc.value_classification,
        "complexity_score": proc.complexity_score,
        "automation_potential": proc.automation_potential,
        "estimated_duration": proc.estimated_duration,
        "estimated_frequency": proc.estimated_frequency,
        "sequencing": dict(proc.sequencing) if proc.sequencing is not None else {},
        "confidence_score": proc.confidence_score,
        "needs_review": proc.needs_review,
        "recommendation_type": "discovered",
    }


def _domain_label(proc: BusinessProcess) -> str:
    if proc.parent is not None and proc.parent.name:
        return proc.parent.name
    return proc.name or "Unassigned"


async def _latest_completed_discovery_run(
    org_id: UUID, db: AsyncSession
) -> DiscoveryRun | None:
    res = await db.execute(
        select(DiscoveryRun)
        .where(
            DiscoveryRun.org_id == org_id,
            DiscoveryRun.status == "completed",
        )
        .order_by(DiscoveryRun.completed_at.desc().nulls_last())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def _gap_process_ids_for_run(
    org_id: UUID, discovery_run_id: UUID, db: AsyncSession
) -> set[UUID]:
    res = await db.execute(
        select(ProcessHandoff.source_process_id, ProcessHandoff.target_process_id).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == discovery_run_id,
            ProcessHandoff.is_gap.is_(True),
        )
    )
    out: set[UUID] = set()
    for src, tgt in res.all():
        out.add(src)
        out.add(tgt)
    return out


def _should_include_process(proc: BusinessProcess) -> bool:
    ap = (proc.automation_potential or "").lower()
    vc = (proc.value_classification or "").upper()
    if ap == "low" and vc == "VA":
        return False
    return True


async def generate_discovered_candidates(org_id: UUID, db: AsyncSession) -> list[dict]:
    run = await _latest_completed_discovery_run(org_id, db)
    if run is None:
        return []

    gap_ids = await _gap_process_ids_for_run(org_id, run.id, db)

    proc_res = await db.execute(
        select(BusinessProcess)
        .where(
            BusinessProcess.org_id == org_id,
            BusinessProcess.discovery_run_id == run.id,
            BusinessProcess.level.in_(("process", "subprocess")),
        )
        .options(selectinload(BusinessProcess.parent))
    )
    processes = proc_res.scalars().unique().all()

    candidates: list[dict] = []
    for proc in processes:
        if not _should_include_process(proc):
            continue
        row = _process_to_base_dict(proc)
        row["domain_name"] = _domain_label(proc)
        row["has_handoff_gap"] = proc.id in gap_ids
        row["automation_type"] = classify_automation_type(row)
        candidates.append(row)
    return candidates


def _build_synthesis_prompt(
    grouped: dict[str, list[dict]],
    handoffs_payload: list[dict],
) -> str:
    grouped_json = json.dumps(grouped, indent=2, default=str)
    handoffs_json = json.dumps(handoffs_payload, indent=2, default=str)
    return f"""You are analyzing discovered business processes and handoffs for cross-process (composite) automation opportunities.

Processes grouped by domain (parent process name):
{grouped_json}

Process handoffs for this discovery run (source_process_id, target_process_id, is_gap, description):
{handoffs_json}

Identify composite automation opportunities that span multiple processes or close handoff gaps. Prefer concrete, automatable bundles tied to the process IDs provided.

Return ONLY valid JSON with this shape:
{{
  "synthesized_candidates": [
    {{
      "title": "Short name for the composite opportunity",
      "description": "What to automate across processes",
      "rationale": "Why this bundle matters",
      "linked_process_ids": ["uuid-string", "..."],
      "automation_type": "deterministic" | "agentic" | "hybrid"
    }}
  ]
}}

Rules:
- linked_process_ids must be a subset of process ids from the input groups.
- Use automation_type "hybrid" when unsure.
- If no strong composite opportunities exist, return an empty synthesized_candidates array.
"""


def _normalize_synthesized_item(raw: dict) -> dict | None:
    title = (raw.get("title") or raw.get("name") or "").strip()
    if not title:
        return None
    ids = raw.get("linked_process_ids") or raw.get("process_ids") or []
    linked: list[str] = []
    for x in ids:
        linked.append(str(x))
    auto = (raw.get("automation_type") or "hybrid").lower().strip()
    if auto not in ("deterministic", "agentic", "hybrid"):
        auto = "hybrid"
    return {
        "name": title,
        "title": title,
        "description": raw.get("description"),
        "narrative": raw.get("rationale") or raw.get("narrative"),
        "linked_process_ids": linked,
        "automation_type": auto,
        "recommendation_type": "synthesized",
        "decision_logic": [],
        "trigger_conditions": [],
        "system_touchpoints": [],
        "failure_modes": [],
        "evidence_sources": [],
        "actors": [],
    }


async def generate_synthesized_candidates(
    org_id: UUID, discovered: list[dict], db: AsyncSession
) -> list[dict]:
    if not discovered:
        return []

    run = await _latest_completed_discovery_run(org_id, db)
    if run is None:
        return []

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in discovered:
        domain = row.get("domain_name") or "Unassigned"
        slim = {
            "id": str(row["id"]),
            "name": row.get("name"),
            "level": row.get("level"),
            "description": row.get("description"),
            "automation_potential": row.get("automation_potential"),
            "value_classification": row.get("value_classification"),
            "automation_type": row.get("automation_type"),
            "has_handoff_gap": row.get("has_handoff_gap"),
        }
        grouped[domain].append(slim)

    ho_res = await db.execute(
        select(ProcessHandoff).where(
            ProcessHandoff.org_id == org_id,
            ProcessHandoff.discovery_run_id == run.id,
        )
    )
    handoffs = ho_res.scalars().all()
    handoffs_payload = [
        {
            "source_process_id": str(h.source_process_id),
            "target_process_id": str(h.target_process_id),
            "is_gap": h.is_gap,
            "description": h.description,
            "handoff_type": h.handoff_type,
        }
        for h in handoffs
    ]

    prompt = _build_synthesis_prompt(dict(grouped), handoffs_payload)

    from app.services.ai.router import llm_call, parse_json_response

    try:
        result = llm_call(
            prompt=prompt,
            max_tokens=8192,
            tier="strong",
            operation="recommendations",
        )
        data = parse_json_response(result.text)
    except Exception:
        logger.exception("synthesized_candidates_llm_failed org_id=%s", org_id)
        return []

    if isinstance(data, dict):
        items = (
            data.get("synthesized_candidates")
            or data.get("candidates")
            or data.get("opportunities")
            or []
        )
    elif isinstance(data, list):
        items = data
    else:
        items = []

    allowed_ids = {str(r["id"]) for r in discovered}
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_synthesized_item(item)
        if not normalized:
            continue
        linked = [x for x in normalized["linked_process_ids"] if x in allowed_ids]
        normalized["linked_process_ids"] = linked
        if len(linked) < 2:
            continue
        normalized["org_id"] = org_id
        normalized["discovery_run_id"] = run.id
        out.append(normalized)
    return out
