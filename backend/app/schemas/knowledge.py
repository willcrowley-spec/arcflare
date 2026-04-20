from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConceptResponse(BaseModel):
    id: UUID
    name: str
    display_name: str | None
    concept_type: str
    frequency: int

    model_config = {"from_attributes": True}


class CommunityResponse(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    label: str | None
    level: int
    source: str
    member_concept_ids: list[str]
    metadata_json: dict
    summary: str | None = None

    model_config = {"from_attributes": True}


class ProvenanceResponse(BaseModel):
    id: UUID
    process_id: UUID
    document_id: UUID
    chunk_ids: list[str]
    relevance_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
