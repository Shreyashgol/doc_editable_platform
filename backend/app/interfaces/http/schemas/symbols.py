from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ....domain.entities import Symbol, SymbolVersion
from ....domain.enums import PropertyValueType, SymbolType


class BBoxModel(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class PropertyView(BaseModel):
    key: str
    value_type: PropertyValueType
    value: Any


class SymbolResponse(BaseModel):
    id: UUID
    document_id: UUID
    page_number: int
    type: str
    label: str | None
    bbox: BBoxModel
    centroid: dict[str, float]
    rotation: float
    crop_uri: str
    classification_method: str | None
    classification_confidence: float | None
    has_embedding: bool
    version: int
    properties: list[PropertyView]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, s: Symbol) -> SymbolResponse:
        return cls(
            id=s.id,
            document_id=s.document_id,
            page_number=s.page_number,
            type=s.symbol_type.value,
            label=s.label,
            bbox=BBoxModel(**s.bbox.to_dict()),
            centroid={"x": s.centroid.x, "y": s.centroid.y},
            rotation=s.rotation,
            crop_uri=s.crop_uri,
            classification_method=(
                s.classification_method.value if s.classification_method else None
            ),
            classification_confidence=s.classification_confidence,
            has_embedding=s.embedding is not None,
            version=s.version,
            properties=[
                PropertyView(key=p.key, value_type=p.value_type, value=p.value)
                for p in s.properties
            ],
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class EditSymbolRequest(BaseModel):
    bbox: BBoxModel | None = None
    rotation: float | None = None
    type: SymbolType | None = None
    label: str | None = None
    reason: str = "manual edit"


class PropertyInputModel(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value_type: PropertyValueType
    value: Any


class UpsertPropertiesRequest(BaseModel):
    properties: list[PropertyInputModel]


class SymbolVersionResponse(BaseModel):
    version: int
    snapshot: dict
    changed_by: UUID | None
    change_reason: str
    created_at: datetime

    @classmethod
    def from_domain(cls, v: SymbolVersion) -> SymbolVersionResponse:
        return cls(
            version=v.version,
            snapshot=v.snapshot,
            changed_by=v.changed_by,
            change_reason=v.change_reason,
            created_at=v.created_at,
        )
