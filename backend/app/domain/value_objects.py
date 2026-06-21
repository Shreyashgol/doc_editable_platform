"""Immutable value objects. No identity, compared by value, validated on construction."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .enums import ClassificationMethod, ProcessingStage, SymbolType


@dataclass(frozen=True, slots=True)
class Centroid:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class BBox:
    """Axis-aligned bounding box in page-pixel space (origin top-left)."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("BBox width and height must be positive")
        if self.x < 0 or self.y < 0:
            raise ValueError("BBox origin must be non-negative")

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def centroid(self) -> Centroid:
        return Centroid(self.x + self.width / 2.0, self.y + self.height / 2.0)

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def iou(self, other: BBox) -> float:
        """Intersection-over-union with another box. Used for dedupe/NMS in extraction."""
        ix = max(self.x, other.x)
        iy = max(self.y, other.y)
        ir = min(self.right, other.right)
        ib = min(self.bottom, other.bottom)
        iw = max(0.0, ir - ix)
        ih = max(0.0, ib - iy)
        intersection = iw * ih
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0

    def contains(self, point: Centroid) -> bool:
        return self.x <= point.x <= self.right and self.y <= point.y <= self.bottom

    def distance_to(self, point: Centroid) -> float:
        """Euclidean distance from this box's centroid to a point (label association)."""
        c = self.centroid
        return ((c.x - point.x) ** 2 + (c.y - point.y) ** 2) ** 0.5

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> BBox:
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )


@dataclass(frozen=True, slots=True)
class Classification:
    """Outcome of a classifier: what it decided, how, and how confident."""

    symbol_type: SymbolType
    method: ClassificationMethod
    confidence: float
    raw_class: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class OcrToken:
    """A recognised text token with its box and confidence on a page."""

    text: str
    bbox: BBox
    confidence: float

    @property
    def centroid(self) -> Centroid:
        return self.bbox.centroid


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    """A unit of work leased from the Postgres queue for a worker to execute (ADR 0005)."""

    task_id: UUID
    document_id: UUID
    stage: ProcessingStage
    attempts: int
    max_attempts: int
    payload: dict[str, object]

    @property
    def is_last_attempt(self) -> bool:
        return self.attempts >= self.max_attempts


@dataclass(frozen=True, slots=True)
class SymbolCandidate:
    """Raw output of the CV extraction stage, before persistence as a Symbol."""

    page_number: int
    bbox: BBox
    crop_uri: str

    @property
    def centroid(self) -> Centroid:
        return self.bbox.centroid
