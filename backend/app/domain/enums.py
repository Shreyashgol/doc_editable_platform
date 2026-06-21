"""Domain enumerations and the document processing state machine definition."""

from __future__ import annotations

from enum import Enum


class ProcessingStatus(str, Enum):
    """States a Document moves through. See docs/02 for the full diagram."""

    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"  # PDF parse + symbol extraction
    OCR_RUNNING = "OCR_RUNNING"
    CLASSIFYING = "CLASSIFYING"
    EMBEDDING = "EMBEDDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES: frozenset[ProcessingStatus] = frozenset(
    {ProcessingStatus.COMPLETED, ProcessingStatus.FAILED, ProcessingStatus.CANCELLED}
)

# Allowed forward transitions. RETRYING can re-enter any active processing stage; FAILED is
# reachable from any non-terminal state; CANCELLED from any non-terminal state.
_ACTIVE_STAGES: frozenset[ProcessingStatus] = frozenset(
    {
        ProcessingStatus.PROCESSING,
        ProcessingStatus.OCR_RUNNING,
        ProcessingStatus.CLASSIFYING,
        ProcessingStatus.EMBEDDING,
    }
)

ALLOWED_TRANSITIONS: dict[ProcessingStatus, frozenset[ProcessingStatus]] = {
    ProcessingStatus.UPLOADED: frozenset({ProcessingStatus.VALIDATING, ProcessingStatus.CANCELLED}),
    ProcessingStatus.VALIDATING: frozenset(
        {ProcessingStatus.QUEUED, ProcessingStatus.FAILED, ProcessingStatus.CANCELLED}
    ),
    ProcessingStatus.QUEUED: frozenset(
        {ProcessingStatus.PROCESSING, ProcessingStatus.FAILED, ProcessingStatus.CANCELLED}
    ),
    ProcessingStatus.PROCESSING: frozenset(
        {
            ProcessingStatus.OCR_RUNNING,
            ProcessingStatus.RETRYING,
            ProcessingStatus.FAILED,
            ProcessingStatus.CANCELLED,
        }
    ),
    ProcessingStatus.OCR_RUNNING: frozenset(
        {
            ProcessingStatus.CLASSIFYING,
            ProcessingStatus.RETRYING,
            ProcessingStatus.FAILED,
            ProcessingStatus.CANCELLED,
        }
    ),
    ProcessingStatus.CLASSIFYING: frozenset(
        {
            ProcessingStatus.EMBEDDING,
            ProcessingStatus.RETRYING,
            ProcessingStatus.FAILED,
            ProcessingStatus.CANCELLED,
        }
    ),
    ProcessingStatus.EMBEDDING: frozenset(
        {
            ProcessingStatus.COMPLETED,
            ProcessingStatus.RETRYING,
            ProcessingStatus.FAILED,
            ProcessingStatus.CANCELLED,
        }
    ),
    # RETRYING returns to whichever active stage is being retried.
    ProcessingStatus.RETRYING: _ACTIVE_STAGES
    | {ProcessingStatus.FAILED, ProcessingStatus.CANCELLED},
    ProcessingStatus.COMPLETED: frozenset(),
    ProcessingStatus.FAILED: frozenset({ProcessingStatus.QUEUED}),  # explicit reprocess
    ProcessingStatus.CANCELLED: frozenset(),
}


class ProcessingStage(str, Enum):
    """Pipeline stage identifiers — used for idempotency keys and job tracking."""

    VALIDATE = "validate"
    PDF_EXTRACT = "pdf_extract"
    OCR = "ocr"
    CLASSIFY = "classify"
    EMBED = "embed"
    GRAPH = "graph"
    FINALIZE = "finalize"


class SymbolType(str, Enum):
    """Known engineering symbol classes. Open for extension; UNKNOWN is the default."""

    VALVE = "Valve"
    PRESSURE_VESSEL = "PressureVessel"
    HEAT_EXCHANGER = "HeatExchanger"
    PRESSURE_TRANSMITTER = "PressureTransmitter"
    CONTROLLER = "Controller"
    PUMP = "Pump"
    COMPRESSOR = "Compressor"
    TANK = "Tank"
    INSTRUMENT = "Instrument"
    PIPE_FITTING = "PipeFitting"
    UNKNOWN = "Unknown"


class ClassificationMethod(str, Enum):
    RULE = "rule"
    ML = "ml"
    VIT = "vit"


class RelationshipType(str, Enum):
    FEEDS = "feeds"
    CONTROLS = "controls"
    MEASURES = "measures"
    CONNECTS_TO = "connects_to"
    PART_OF = "part_of"
    REGULATES = "regulates"


class Role(str, Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"


class PropertyValueType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOL = "bool"
    DATE = "date"
    JSON = "json"
