"""Deprecated legacy recommendation scorer.

The active recommendation pipeline writes agent opportunities through
``pipeline.py`` and computes ARC Score through ``recompute.py``. This module is
kept temporarily for import compatibility only.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.models.recommendation import Recommendation


def score_recommendation(patterns: dict) -> list[Recommendation]:
    """
    Turn analyzer patterns into persisted Recommendation ORM rows (unsaved).

    Caller is responsible for adding to session and committing.
    """
    org_id = UUID(str(patterns["org_id"]))
    candidates: list[Recommendation] = []
    if patterns.get("custom_object_count", 0) > 0:
        candidates.append(
            Recommendation(
                org_id=org_id,
                title="Rationalize custom objects",
                description="High number of custom objects increases maintenance cost.",
                priority="medium",
                category="metadata",
                estimated_roi=None,
                composite_score=0.72,
                status="active",
                analysis_inputs_json=[patterns],
                actions_json=[{"type": "review_metadata"}],
                impact_json={"maintenance": "high"},
                architecture_health_json={"objects": patterns.get("metadata_object_count", 0)},
                linked_process_ids=[],
                generated_at=datetime.now(tz=UTC),
                implemented_at=None,
            )
        )
    return candidates
