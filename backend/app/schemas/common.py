from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination wrapper for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    pages: int = 1
