"""Response envelope + error body shared by every router (08 §1).

Every response that carries numbers uses ``Envelope[T]`` with a ``Meta`` that
states ``data_as_of``, ``computed_at``, ``compute_state`` and ``confidence``.
Datetimes are serialised as ISO 8601 with the ``+07:00`` offset.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, PlainSerializer

from app.core.timeutil import iso_local

ComputeState = Literal["fresh", "queued", "computing", "stale", "failed"]
Confidence = Literal["verified", "reference", "scenario"]

LocalDatetime = Annotated[
    datetime,
    PlainSerializer(lambda v: iso_local(v), return_type=str, when_used="json"),
]

T = TypeVar("T")


class SourceRef(BaseModel):
    id: str
    kind: str
    label: str


class Meta(BaseModel):
    data_as_of: LocalDatetime | None = None
    computed_at: LocalDatetime | None = None
    compute_state: ComputeState | None = None
    confidence: Confidence | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta = Field(default_factory=Meta)


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    error: ErrorInfo
