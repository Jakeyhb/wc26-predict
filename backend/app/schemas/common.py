from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class APIMessage(BaseModel):
    status: str
    detail: str | None = None


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    pagination: PaginationMeta


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    name_zh: str | None = None
    fifa_code: str | None = None


class AuditStamp(BaseModel):
    created_at: datetime
    updated_at: datetime | None = None

