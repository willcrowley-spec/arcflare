"""Backfill typed metadata bindings for existing recommendations.

Dry-run is the default. Use --apply to persist recommendation JSON updates.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.models.metadata import MetadataObject
from app.models.process import BusinessProcess
from app.models.recommendation import Recommendation
from app.services.recommendations.arc_score import apply_arc_score
from app.services.recommendations.metadata_bindings import build_metadata_bindings


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _process_contexts(processes: list[BusinessProcess]) -> list[dict]:
    by_parent: dict[str, list[BusinessProcess]] = defaultdict(list)
    for proc in processes:
        if proc.parent_id:
            by_parent[str(proc.parent_id)].append(proc)

    contexts = []
    for proc in processes:
        contexts.append(
            {
                "id": str(proc.id),
                "name": proc.name,
                "level": proc.level,
                "system_touchpoints": proc.system_touchpoints or [],
                "steps": [
                    {
                        "id": str(child.id),
                        "name": child.name,
                        "level": child.level,
                        "system_touchpoints": child.system_touchpoints or [],
                    }
                    for child in by_parent.get(str(proc.id), [])
                ],
            }
        )
    return contexts


def _recommendation_opportunity(rec: Recommendation) -> dict:
    opportunity = dict(rec.agent_opportunity_json or {})
    if opportunity.get("replaces"):
        return opportunity
    if rec.linked_process_ids or rec.linked_step_ids:
        opportunity["replaces"] = [
            {
                "process_id": str(rec.linked_process_ids[0]) if rec.linked_process_ids else "",
                "process_name": "",
                "steps_replaced": [],
                "step_ids": [str(sid) for sid in (rec.linked_step_ids or []) if sid],
                "replacement_type": "partial",
            }
        ]
    return opportunity


async def _load_org_context(session, org_id: UUID) -> tuple[dict, list[dict]]:
    objects_q = await session.execute(
        select(MetadataObject)
        .where(MetadataObject.org_id == org_id)
        .options(selectinload(MetadataObject.fields))
        .order_by(MetadataObject.api_name)
    )
    objects = list(objects_q.scalars().unique().all())
    metadata = {
        "objects": [
            {
                "api_name": obj.api_name,
                "label": obj.label,
                "fields": [{"api_name": field.api_name, "label": field.label} for field in (obj.fields or [])],
            }
            for obj in objects
        ]
    }

    processes_q = await session.execute(
        select(BusinessProcess)
        .where(BusinessProcess.org_id == org_id)
        .order_by(BusinessProcess.level, BusinessProcess.name)
    )
    process_contexts = _process_contexts(list(processes_q.scalars().all()))
    return metadata, process_contexts


def _summary(payload: dict) -> dict:
    telemetry = payload.get("telemetry") or {}
    source_counts: dict[str, int] = defaultdict(int)
    for binding in _as_list(payload.get("bindings")):
        source_counts[str(binding.get("source") or "unknown")] += 1
    unresolved_reasons: dict[str, int] = defaultdict(int)
    unresolved_types: dict[str, int] = defaultdict(int)
    for binding in _as_list(payload.get("unresolved_bindings")):
        unresolved_reasons[str(binding.get("reason") or "unknown")] += 1
        unresolved_types[str(binding.get("ref_type") or "unknown")] += 1
    return {
        "validated": sum(1 for b in _as_list(payload.get("bindings")) if b.get("status") == "validated"),
        "suggested": sum(1 for b in _as_list(payload.get("bindings")) if b.get("status") == "suggested"),
        "unresolved": len(_as_list(payload.get("unresolved_bindings"))),
        "source_counts": dict(sorted(source_counts.items())),
        "unresolved_reasons": dict(sorted(unresolved_reasons.items())),
        "unresolved_types": dict(sorted(unresolved_types.items())),
        "telemetry": telemetry,
    }


async def _run(args: argparse.Namespace) -> dict:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            filters = [Recommendation.recommendation_type == "agent_opportunity"]
            if args.org_id:
                filters.append(Recommendation.org_id == UUID(args.org_id))

            stmt = select(Recommendation).where(*filters).order_by(Recommendation.generated_at.desc())
            if args.limit:
                stmt = stmt.limit(args.limit)

            rows = list((await session.execute(stmt)).scalars().all())
            org_cache: dict[UUID, tuple[dict, list[dict]]] = {}
            details = []
            totals = {
                "validated": 0,
                "suggested": 0,
                "unresolved": 0,
                "already_had_bindings": 0,
                "updated": 0,
                "source_counts": {},
                "unresolved_reasons": {},
                "unresolved_types": {},
            }
            for rec in rows:
                if rec.org_id not in org_cache:
                    org_cache[rec.org_id] = await _load_org_context(session, rec.org_id)
                metadata, process_contexts = org_cache[rec.org_id]

                opportunity = _recommendation_opportunity(rec)
                existing = opportunity.get("metadata_bindings_v1")
                if isinstance(existing, dict) and existing.get("schema_version") == "metadata_bindings_v1":
                    totals["already_had_bindings"] += 1

                payload = build_metadata_bindings(
                    opportunity,
                    process_contexts=process_contexts,
                    salesforce_metadata=metadata,
                )
                summary = _summary(payload)
                for key in ("validated", "suggested", "unresolved"):
                    totals[key] += int(summary[key])
                for key in ("source_counts", "unresolved_reasons", "unresolved_types"):
                    for name, count in summary[key].items():
                        totals[key][name] = totals[key].get(name, 0) + count

                details.append(
                    {
                        "id": str(rec.id),
                        "title": rec.title,
                        "status": rec.status,
                        "existing_binding_count": len(_as_list(existing.get("bindings"))) if isinstance(existing, dict) else 0,
                        "after": summary,
                    }
                )

                if args.apply:
                    opportunity["metadata_bindings_v1"] = payload
                    opportunity["binding_model_version"] = payload["binding_model_version"]
                    impact = dict(rec.impact_json or {})
                    impact["metadata_bindings_v1"] = payload
                    impact["binding_model_version"] = payload["binding_model_version"]
                    rec.agent_opportunity_json = opportunity
                    rec.impact_json = impact
                    apply_arc_score(rec)
                    totals["updated"] += 1

            if args.apply:
                await session.commit()
            else:
                await session.rollback()

            return {
                "mode": "apply" if args.apply else "dry_run",
                "count": len(rows),
                "totals": totals,
                "details": details,
            }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", help="Optional Arcflare organization UUID to scope the backfill.")
    parser.add_argument("--limit", type=int, help="Optional maximum rows to inspect/update.")
    parser.add_argument("--apply", action="store_true", help="Persist changes. Omit for dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Explicit no-op mode; this is the default.")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        raise SystemExit("Use either --apply or --dry-run, not both.")
    print(json.dumps(asyncio.run(_run(args)), indent=2, default=str))


if __name__ == "__main__":
    main()
