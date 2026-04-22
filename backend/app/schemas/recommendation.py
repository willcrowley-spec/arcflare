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
    recommendation_type: str
    automation_type: str
    base_score: float | None
    llm_score: float | None
    llm_rationale: str | None
    score_divergence_flag: bool
    assumptions_json: dict
    scenarios_json: dict
    enrichment_log: list
    agent_opportunity_json: dict
    linked_step_ids: list
    domain_id: UUID | None
    financial_evaluation_status: str
    recommendation_run_id: UUID | None
    generated_at: datetime
    implemented_at: datetime | None


class RecommendationSummary(BaseModel):
    total: int
    active: int
    implemented: int
    avg_roi: float | None
    avg_npv: float | None
    top_category: str | None
    by_automation_type: dict | None


class RecommendationStatusUpdate(BaseModel):
    status: str = Field(..., max_length=50)


class RecalculateRequest(BaseModel):
    overrides: dict


class PortfolioProjectionRequest(BaseModel):
    recommendation_ids: list[UUID]
    global_overrides: dict = Field(default_factory=dict)


class PortfolioProjectionResponse(BaseModel):
    optimistic: dict
    expected: dict
    conservative: dict
    npv: dict
    payback_month: dict
    recommendation_count: int
    by_automation_type: dict[str, int] | None = None


class RecommendationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    status: str
    config: dict
    stage_results: dict
    error: str | None
    started_at: datetime
    completed_at: datetime | None
