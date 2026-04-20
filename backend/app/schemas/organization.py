from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrgProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    clerk_org_id: str
    plan_tier: str
    settings_json: dict
    created_at: datetime
    updated_at: datetime


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    entity_type: str | None
    parent_id: UUID | None
    department: str | None
    title: str | None
    role: str | None
    headcount: int
    is_active: bool
    salesforce_user_id: str | None
    cost_data_json: dict
    metadata_json: dict
    created_at: datetime


class EntityCreate(BaseModel):
    name: str = Field(..., max_length=255)
    entity_type: str | None = Field(default=None, max_length=50)
    parent_id: UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    headcount: int = Field(default=1, ge=0)
    is_active: bool = True
    salesforce_user_id: str | None = Field(default=None, max_length=18)


class EntityUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    entity_type: str | None = Field(default=None, max_length=50)
    parent_id: UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    headcount: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    salesforce_user_id: str | None = Field(default=None, max_length=18)
    cost_data_json: dict | None = None
    metadata_json: dict | None = None


class CostModelResponse(BaseModel):
    org_id: UUID
    annual_cost_deflection: float | None = None
    hires_deflected: float | None = None
    assumptions: dict = Field(default_factory=dict)


class HierarchyNode(BaseModel):
    id: UUID
    name: str
    entity_type: str | None
    children: list["HierarchyNode"] = Field(default_factory=list)


class HierarchyResponse(BaseModel):
    roots: list[HierarchyNode]


class LicenseSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    connection_id: UUID
    snapshot_at: datetime
    edition: str | None
    is_sandbox: bool
    licenses_json: list
    package_licenses_json: list
    psl_json: list
    limits_json: dict
    estimated_annual_spend: float | None


class UserVelocityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    connection_id: UUID
    snapshot_at: datetime
    active_user_count: int
    internal_active_count: int = 0
    external_active_count: int = 0
    system_user_count: int = 0
    by_created_month_json: dict = {}
    new_users_this_month: int
    deactivated_this_month: int
    by_role_json: dict
    by_profile_json: dict


class OrgProfileUpdate(BaseModel):
    """Updatable fields on the org profile (stored in settings_json)."""
    company_name: str | None = None
    domains: list[str] | None = None
    industry: str | None = None
    description: str | None = None
    headcount: int | None = None
    annual_revenue: float | None = None


class OrgResearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    status: str
    profile_json: dict
    sources_json: list
    facts_json: list
    research_log_json: dict
    company_summary: str | None
    industry: str | None
    employee_range: str | None
    revenue_range: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class OrgResearchStatusResponse(BaseModel):
    status: str
    profile_id: str | None = None
    phases: dict = Field(default_factory=dict)
    error: str | None = None
