"""Pydantic schemas for the prompt store API."""

from pydantic import BaseModel, ConfigDict, Field


class PromptBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_type: str
    label: str
    editable: bool
    content: str
    is_customized: bool
    is_locked: bool
    available_vars: list[str]
    version: int


class PromptBlockUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)


class OperationOut(BaseModel):
    operation_id: str
    label: str
    group: str
    blocks: list[dict]


class OperationsListOut(BaseModel):
    operations: list[OperationOut]
