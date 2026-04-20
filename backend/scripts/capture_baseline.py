"""Capture baseline performance metrics for the discovery pipeline.

Queries Langfuse for existing discovery runs and writes a summary to
docs/superpowers/specs/baseline-metrics.json. Run this BEFORE applying
performance optimizations so you have a reference to compare against.

Usage:
    python -m scripts.capture_baseline [--org-id UUID] [--limit 10]
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def gather_run_metrics(org_id: UUID | None = None, limit: int = 10) -> list[dict]:
    """Query recent completed discovery runs and their quality scores."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.discovery import DiscoveryRun

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as session:
            q = select(DiscoveryRun).where(
                DiscoveryRun.status == "completed"
            ).order_by(DiscoveryRun.completed_at.desc()).limit(limit)

            if org_id:
                q = q.where(DiscoveryRun.org_id == org_id)

            result = await session.execute(q)
            runs = result.scalars().all()

            metrics = []
            for run in runs:
                duration_s = None
                if run.completed_at and run.started_at:
                    duration_s = (run.completed_at - run.started_at).total_seconds()

                metrics.append({
                    "run_id": str(run.id),
                    "org_id": str(run.org_id),
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "duration_seconds": duration_s,
                    "pass_results": run.pass_results or {},
                    "stage_results": run.stage_results or {},
                    "quality_scores": run.quality_scores or {},
                })

            return metrics
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Capture discovery pipeline baseline metrics")
    parser.add_argument("--org-id", type=str, default=None, help="Filter to specific org")
    parser.add_argument("--limit", type=int, default=10, help="Max runs to fetch")
    args = parser.parse_args()

    org_id = UUID(args.org_id) if args.org_id else None
    metrics = asyncio.run(gather_run_metrics(org_id, args.limit))

    if not metrics:
        logger.warning("No completed discovery runs found")
        sys.exit(0)

    quality_scores = [m["quality_scores"] for m in metrics if m["quality_scores"]]
    durations = [m["duration_seconds"] for m in metrics if m["duration_seconds"]]

    summary = {
        "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        "run_count": len(metrics),
        "avg_duration_seconds": sum(durations) / len(durations) if durations else None,
        "min_duration_seconds": min(durations) if durations else None,
        "max_duration_seconds": max(durations) if durations else None,
        "avg_quality_overall": (
            sum(q.get("overall", 0) for q in quality_scores) / len(quality_scores)
            if quality_scores else None
        ),
        "quality_score_breakdown": {},
        "runs": metrics,
    }

    if quality_scores:
        all_keys = set()
        for q in quality_scores:
            all_keys.update(q.keys())
        for key in sorted(all_keys):
            vals = [q.get(key, 0) for q in quality_scores if key in q]
            if vals:
                summary["quality_score_breakdown"][key] = {
                    "avg": round(sum(vals) / len(vals), 4),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                }

    out_path = Path(__file__).parent.parent.parent / "docs" / "superpowers" / "specs" / "baseline-metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    logger.info("Baseline written to %s (%d runs)", out_path, len(metrics))


if __name__ == "__main__":
    main()
