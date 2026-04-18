from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DiscoveryRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    pass_results: dict
    config: dict
    created_by: str
    error: str | None
    quality_scores: dict = {}
    stage_results: dict = {}


class ProcessHandoffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    source_process_id: UUID
    target_process_id: UUID
    handoff_type: str
    description: str | None
    confidence_score: float
    is_gap: bool
    needs_review: bool
    gap_status: str = "open"
    resolution_note: str | None = None
    discovery_run_id: UUID | None
    metadata_json: dict


class DiscoveryStatusResponse(BaseModel):
    run_id: str | None
    status: str
    phases: dict
    started_at: str | None
    completed_at: str | None
    error: str | None
