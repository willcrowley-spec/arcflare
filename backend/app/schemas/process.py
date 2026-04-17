from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcessKpis(BaseModel):
    total_processes: int = 0
    avg_efficiency: float | None = None
    draft_count: int = 0
    published_count: int = 0
    domain_count: int = 0
    needs_review_count: int = 0
    handoff_count: int = 0
    gap_count: int = 0


class ProcessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    category: str | None
    description: str | None
    efficiency_score: float | None
    automation_level: str | None
    status: str
    source: str | None
    sub_process_count: int
    managed_asset_count: int
    metadata_json: dict
    created_at: datetime
    parent_id: UUID | None = None
    level: str = "process"
    confidence_score: float | None = None
    needs_review: bool = False
    narrative: str | None = None
    discovery_run_id: UUID | None = None
    actors: list = []
    artifacts: list = []


class ProcessCreate(BaseModel):
    name: str = Field(..., max_length=255)
    category: str | None = Field(default=None, max_length=255)
    description: str | None = None
    automation_level: str | None = Field(default=None, max_length=50)
    status: str = Field(default="draft", max_length=50)
    source: str | None = Field(default=None, max_length=50)


class ProcessUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    description: str | None = None
    efficiency_score: float | None = None
    automation_level: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=50)
    metadata_json: dict | None = None


class ProcessNodeUpdate(BaseModel):
    node_id: UUID
    position_x: float
    position_y: float
    label: str | None = None
    subtitle: str | None = None
    metadata_json: dict | None = None


class ProcessExportRequest(BaseModel):
    format: str = Field(default="json", pattern="^(json|svg|lucidchart)$")
