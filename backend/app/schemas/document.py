from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str | None
    file_size_bytes: int | None
    storage_path: str | None
    status: str
    chunk_count: int
    content_hash: str | None = None
    concept_count: int = 0
    community_ids: list = Field(default_factory=list)
    embedding_model: str | None = None
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    filename: str
    mime_type: str | None
    file_size_bytes: int | None
    storage_path: str | None
    status: str
    error_message: str | None
    uploaded_by: UUID | None
    tags: list
    chunk_count: int
    content_hash: str | None = None
    concept_count: int = 0
    community_ids: list = Field(default_factory=list)
    embedding_model: str | None = None
    created_at: datetime


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    top_k: int = Field(default=8, ge=1, le=50)


class DocumentSearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str | None
    score: float
    page_number: int | None
    section_title: str | None
