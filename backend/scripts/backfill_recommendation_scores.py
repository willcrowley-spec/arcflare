"""Backfill recommendation financial projections and ARC Score payloads.

Dry-run is the default. Use --apply to persist changes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.models.recommendation import Recommendation
from app.services.recommendations.recompute import recompute_recommendation


def _round_money(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _before_snapshot(rec: Recommendation) -> dict[str, Any]:
    scenarios = rec.scenarios_json if isinstance(rec.scenarios_json, dict) else {}
    assumptions = rec.assumptions_json if isinstance(rec.assumptions_json, dict) else {}
    return {
        "id": str(rec.id),
        "title": rec.title,
        "status": rec.status,
        "automation_type": rec.automation_type,
        "arc_score": (rec.arc_score_json or {}).get("score"),
        "composite_score": rec.composite_score,
        "expected_npv": (scenarios.get("npv") or {}).get("expected"),
        "expected_investment": (scenarios.get("expected") or {}).get("total_investment"),
        "technology_cost": assumptions.get("technology_cost"),
    }


def _delta(before: dict[str, Any], rec: Recommendation) -> dict[str, Any]:
    scenarios = rec.scenarios_json if isinstance(rec.scenarios_json, dict) else {}
    assumptions = rec.assumptions_json if isinstance(rec.assumptions_json, dict) else {}
    after_npv = (scenarios.get("npv") or {}).get("expected")
    after_investment = (scenarios.get("expected") or {}).get("total_investment")
    return {
        **before,
        "after_arc_score": (rec.arc_score_json or {}).get("score"),
        "after_expected_npv": after_npv,
        "after_expected_investment": after_investment,
        "after_technology_cost": assumptions.get("technology_cost"),
        "npv_delta": (
            _round_money(float(after_npv) - float(before["expected_npv"]))
            if before.get("expected_npv") is not None and after_npv is not None
            else None
        ),
        "investment_delta": (
            _round_money(float(after_investment) - float(before["expected_investment"]))
            if before.get("expected_investment") is not None and after_investment is not None
            else None
        ),
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            filters = []
            if args.org_id:
                filters.append(Recommendation.org_id == UUID(args.org_id))

            stmt = select(Recommendation).where(*filters).order_by(Recommendation.generated_at.desc())
            if args.limit:
                stmt = stmt.limit(args.limit)

            rows = list((await session.execute(stmt)).scalars().all())
            details: list[dict[str, Any]] = []
            for rec in rows:
                before = _before_snapshot(rec)
                recompute_recommendation(rec)
                details.append(_delta(before, rec))

            if args.apply:
                await session.commit()
            else:
                await session.rollback()

            return {
                "mode": "apply" if args.apply else "dry_run",
                "count": len(rows),
                "updated": len(details) if args.apply else 0,
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
