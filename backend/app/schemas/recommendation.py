from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    title: str
    description: str | None
    priority: str | None
    category: str | None
    estimated_roi: Decimal | None
    composite_score: float | None
    status: str
    analysis_inputs_json: list
    actions_json: list
    impact_json: dict
    architecture_health_json: dict
    linked_process_ids: list
    generated_at: datetime
    implemented_at: datetime | None


class RecommendationSummary(BaseModel):
    total: int
    active: int
    implemented: int
    avg_roi: float | None
    top_category: str | None


class RecommendationStatusUpdate(BaseModel):
    status: str = Field(..., max_length=50)
