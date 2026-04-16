from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=100)
    monthly_cap: Decimal | None = None
    status: str | None = Field(default=None, max_length=50)
    capability_tags: list[str] | None = None
    config_json: dict | None = None


class AgentCreate(BaseModel):
    name: str = Field(..., max_length=255)
    model: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=100)
    monthly_cap: Decimal | None = None
    capability_tags: list[str] = Field(default_factory=list)
    config_json: dict = Field(default_factory=dict)
    linked_recommendation_id: UUID | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    model: str | None
    model_version: str | None
    monthly_cap: Decimal | None
    total_spend: Decimal
    total_tokens: int
    status: str
    accuracy: float
    tasks_completed: int
    capability_tags: list
    config_json: dict
    linked_recommendation_id: UUID | None
    created_at: datetime


class AgentUsageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    task_type: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost: Decimal | None
    duration_ms: int | None
    success: bool | None
    logged_at: datetime


class FleetKpis(BaseModel):
    total_agents: int = 0
    active_agents: int = 0
    total_spend: Decimal = Decimal("0")
    total_tokens: int = 0
    total_tasks: int = 0


class FleetAnalyticsResponse(BaseModel):
    kpis: FleetKpis
    by_status: dict[str, int] = Field(default_factory=dict)
    by_model: dict[str, int] = Field(default_factory=dict)
