"""Translation between ORM models and domain entities.

Pure functions, no I/O. They are the only place that knows both shapes, so the rest of the
codebase deals exclusively in domain objects.
"""

from __future__ import annotations

from ...domain.entities import (
    AuditLog,
    Document,
    Page,
    ProcessingJob,
    Relationship,
    Symbol,
    SymbolProperty,
    SymbolVersion,
    User,
)
from ...domain.enums import (
    ClassificationMethod,
    ProcessingStage,
    ProcessingStatus,
    PropertyValueType,
    RelationshipType,
    Role,
    SymbolType,
)
from ...domain.value_objects import BBox
from . import models as m


def document_to_domain(row: m.DocumentModel) -> Document:
    return Document(
        id=row.id,
        owner_id=row.owner_id,
        filename=row.filename,
        content_hash=row.content_hash,
        storage_uri=row.storage_uri,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        status=ProcessingStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def document_apply_to_row(doc: Document, row: m.DocumentModel) -> None:
    row.filename = doc.filename
    row.content_hash = doc.content_hash
    row.storage_uri = doc.storage_uri
    row.mime_type = doc.mime_type
    row.size_bytes = doc.size_bytes
    row.page_count = doc.page_count
    row.status = doc.status.value


def document_to_row(doc: Document) -> m.DocumentModel:
    return m.DocumentModel(
        id=doc.id,
        owner_id=doc.owner_id,
        filename=doc.filename,
        content_hash=doc.content_hash,
        storage_uri=doc.storage_uri,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        status=doc.status.value,
    )


def page_to_row(page: Page) -> m.PageModel:
    return m.PageModel(
        id=page.id,
        document_id=page.document_id,
        page_number=page.page_number,
        width_px=page.width_px,
        height_px=page.height_px,
        dpi=page.dpi,
        render_uri=page.render_uri,
    )


def job_to_domain(row: m.ProcessingJobModel) -> ProcessingJob:
    return ProcessingJob(
        id=row.id,
        document_id=row.document_id,
        stage=ProcessingStage(row.stage),
        stage_status=row.stage_status,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        last_error=row.last_error,
        timings=dict(row.timings or {}),
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def job_apply_to_row(job: ProcessingJob, row: m.ProcessingJobModel) -> None:
    row.stage = job.stage.value
    row.stage_status = job.stage_status
    row.attempts = job.attempts
    row.max_attempts = job.max_attempts
    row.last_error = job.last_error
    row.timings = job.timings
    row.started_at = job.started_at
    row.finished_at = job.finished_at


def job_to_row(job: ProcessingJob) -> m.ProcessingJobModel:
    row = m.ProcessingJobModel(id=job.id, document_id=job.document_id, stage=job.stage.value,
                               stage_status=job.stage_status)
    job_apply_to_row(job, row)
    return row


def property_to_domain(row: m.SymbolPropertyModel) -> SymbolProperty:
    return SymbolProperty(
        id=row.id,
        symbol_id=row.symbol_id,
        key=row.key,
        value_type=PropertyValueType(row.value_type),
        value=row.value.get("v") if isinstance(row.value, dict) else row.value,
    )


def symbol_to_domain(row: m.SymbolModel) -> Symbol:
    return Symbol(
        id=row.id,
        document_id=row.document_id,
        page_number=row.page_number,
        bbox=BBox(row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h),
        crop_uri=row.crop_uri,
        symbol_type=SymbolType(row.type),
        label=row.label,
        rotation=row.rotation,
        classification_method=(
            ClassificationMethod(row.classification_method)
            if row.classification_method
            else None
        ),
        classification_confidence=row.classification_confidence,
        embedding=list(row.embedding.embedding) if row.embedding else None,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        properties=[property_to_domain(p) for p in row.properties],
    )


def symbol_to_row(sym: Symbol) -> m.SymbolModel:
    return m.SymbolModel(
        id=sym.id,
        document_id=sym.document_id,
        page_number=sym.page_number,
        type=sym.symbol_type.value,
        label=sym.label,
        bbox_x=sym.bbox.x,
        bbox_y=sym.bbox.y,
        bbox_w=sym.bbox.width,
        bbox_h=sym.bbox.height,
        centroid_x=sym.centroid.x,
        centroid_y=sym.centroid.y,
        rotation=sym.rotation,
        crop_uri=sym.crop_uri,
        classification_method=(
            sym.classification_method.value if sym.classification_method else None
        ),
        classification_confidence=sym.classification_confidence,
        version=sym.version,
    )


def symbol_apply_to_row(sym: Symbol, row: m.SymbolModel) -> None:
    row.type = sym.symbol_type.value
    row.label = sym.label
    row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h = (
        sym.bbox.x,
        sym.bbox.y,
        sym.bbox.width,
        sym.bbox.height,
    )
    row.centroid_x, row.centroid_y = sym.centroid.x, sym.centroid.y
    row.rotation = sym.rotation
    row.classification_method = (
        sym.classification_method.value if sym.classification_method else None
    )
    row.classification_confidence = sym.classification_confidence
    row.version = sym.version


def version_to_row(v: SymbolVersion) -> m.SymbolVersionModel:
    return m.SymbolVersionModel(
        id=v.id,
        symbol_id=v.symbol_id,
        version=v.version,
        snapshot=v.snapshot,
        changed_by=v.changed_by,
        change_reason=v.change_reason,
    )


def version_to_domain(row: m.SymbolVersionModel) -> SymbolVersion:
    return SymbolVersion(
        id=row.id,
        symbol_id=row.symbol_id,
        version=row.version,
        snapshot=row.snapshot,
        changed_by=row.changed_by,
        change_reason=row.change_reason,
        created_at=row.created_at,
    )


def relationship_to_row(r: Relationship) -> m.RelationshipModel:
    return m.RelationshipModel(
        id=r.id,
        document_id=r.document_id,
        source_symbol_id=r.source_symbol_id,
        target_symbol_id=r.target_symbol_id,
        type=r.type.value,
        confidence=r.confidence,
        properties=r.properties,
    )


def relationship_to_domain(row: m.RelationshipModel) -> Relationship:
    return Relationship(
        id=row.id,
        document_id=row.document_id,
        source_symbol_id=row.source_symbol_id,
        target_symbol_id=row.target_symbol_id,
        type=RelationshipType(row.type),
        confidence=row.confidence,
        properties=dict(row.properties or {}),
    )


def audit_to_row(a: AuditLog) -> m.AuditLogModel:
    return m.AuditLogModel(
        id=a.id,
        actor_id=a.actor_id,
        entity_type=a.entity_type,
        entity_id=a.entity_id,
        action=a.action,
        before=a.before,
        after=a.after,
        correlation_id=a.correlation_id,
    )


def audit_to_domain(row: m.AuditLogModel) -> AuditLog:
    return AuditLog(
        id=row.id,
        actor_id=row.actor_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        before=row.before,
        after=row.after,
        correlation_id=row.correlation_id,
        created_at=row.created_at,
    )


def user_to_domain(row: m.UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        roles={Role(r) for r in row.roles},
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def user_to_row(u: User) -> m.UserModel:
    return m.UserModel(
        id=u.id,
        email=u.email,
        password_hash=u.password_hash,
        roles=[r.value for r in u.roles],
        is_active=u.is_active,
    )
