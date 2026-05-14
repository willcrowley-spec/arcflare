from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentDesignPackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    generation_run_id: UUID
    recommendation_id: UUID
    version: int
    status: str
    package_json: dict
    validation_json: dict
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentSourceBundleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    generation_run_id: UUID
    design_package_id: UUID
    status: str
    source_tree_json: dict
    checks_json: dict
    created_at: datetime
    updated_at: datetime


class ScratchValidationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    source_bundle_id: UUID
    status: str
    devhub_alias: str | None
    scratch_org_id: str | None
    scratch_org_username: str | None
    expires_at: datetime | None
    logs_json: list
    result_json: dict
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class AgentGenerationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    recommendation_id: UUID
    status: str
    current_stage: str | None
    model_json: dict
    stage_results: dict
    error: str | None
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None
    updated_at: datetime
    design_package: AgentDesignPackageResponse | None = None
    source_bundle: AgentSourceBundleResponse | None = None
    validation_runs: list[ScratchValidationRunResponse] = Field(default_factory=list)
