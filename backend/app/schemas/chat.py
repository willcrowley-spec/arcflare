"""Pydantic schemas for the chat assistant API."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ThreadCreate(BaseModel):
    anchor_type: str | None = Field(default=None, max_length=50)
    anchor_id: UUID | None = None
    model_override: str | None = Field(default=None, max_length=255)


class ThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    user_id: UUID
    title: str
    anchor_type: str | None
    anchor_id: UUID | None
    model_override: str | None
    summary: str | None
    message_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    items: list[ThreadResponse]
    total: int


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: UUID
    role: str
    content: str
    tool_calls: list | dict = []
    tool_results: list | dict = []
    token_count: int | None
    langfuse_trace_id: str | None
    created_at: datetime


class ActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: UUID
    message_id: UUID
    action_type: str
    target_id: UUID | None
    payload: dict
    status: str
    result: dict | None
    idempotency_key: str
    created_at: datetime
    executed_at: datetime | None


class ActionConfirm(BaseModel):
    payload_edits: dict | None = None


class ThreadDetailResponse(BaseModel):
    thread: ThreadResponse
    messages: list[MessageResponse]
    pending_actions: list[ActionResponse]
