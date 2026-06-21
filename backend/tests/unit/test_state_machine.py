from uuid import uuid4

import pytest

from app.core.errors import IllegalStateTransitionError
from app.domain.entities import Document
from app.domain.enums import ProcessingStatus


def _doc() -> Document:
    return Document(
        owner_id=uuid4(),
        filename="p.pdf",
        content_hash="a" * 64,
        storage_uri="raw/x.pdf",
        mime_type="application/pdf",
        size_bytes=1234,
    )


def test_happy_path_full_pipeline():
    doc = _doc()
    path = [
        ProcessingStatus.VALIDATING,
        ProcessingStatus.QUEUED,
        ProcessingStatus.PROCESSING,
        ProcessingStatus.OCR_RUNNING,
        ProcessingStatus.CLASSIFYING,
        ProcessingStatus.EMBEDDING,
        ProcessingStatus.COMPLETED,
    ]
    for target in path:
        doc.transition_to(target)
    assert doc.status is ProcessingStatus.COMPLETED
    assert doc.status.is_terminal
    assert len(doc.transitions) == len(path)


def test_illegal_transition_raises():
    doc = _doc()
    with pytest.raises(IllegalStateTransitionError):
        doc.transition_to(ProcessingStatus.COMPLETED)


def test_retry_reenters_active_stage():
    doc = _doc()
    for s in (ProcessingStatus.VALIDATING, ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING):
        doc.transition_to(s)
    doc.transition_to(ProcessingStatus.OCR_RUNNING)
    doc.transition_to(ProcessingStatus.RETRYING)
    doc.transition_to(ProcessingStatus.OCR_RUNNING)  # retry re-enters the stage
    assert doc.status is ProcessingStatus.OCR_RUNNING


def test_cancel_from_active_state():
    doc = _doc()
    doc.transition_to(ProcessingStatus.VALIDATING)
    doc.cancel()
    assert doc.status is ProcessingStatus.CANCELLED


def test_cancel_terminal_raises():
    doc = _doc()
    doc.transition_to(ProcessingStatus.VALIDATING)
    doc.transition_to(ProcessingStatus.QUEUED)
    doc.transition_to(ProcessingStatus.PROCESSING)
    doc.transition_to(ProcessingStatus.OCR_RUNNING)
    doc.transition_to(ProcessingStatus.CLASSIFYING)
    doc.transition_to(ProcessingStatus.EMBEDDING)
    doc.transition_to(ProcessingStatus.COMPLETED)
    with pytest.raises(IllegalStateTransitionError):
        doc.cancel()


def test_failed_is_reprocessable():
    doc = _doc()
    doc.transition_to(ProcessingStatus.VALIDATING)
    doc.transition_to(ProcessingStatus.FAILED)
    assert doc.status.is_terminal
    doc.transition_to(ProcessingStatus.QUEUED)  # explicit reprocess
    assert doc.status is ProcessingStatus.QUEUED


def test_mark_failed_noop_when_terminal():
    doc = _doc()
    doc.transition_to(ProcessingStatus.VALIDATING)
    doc.cancel()
    doc.mark_failed("late error")  # should not raise nor change terminal state
    assert doc.status is ProcessingStatus.CANCELLED
