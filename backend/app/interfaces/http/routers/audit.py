from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ....application.security import Principal
from ....application.services.audit_service import AuditService
from ....core.container import Container
from ..deps import get_container, get_principal

router = APIRouter(prefix="/audit", tags=["audit"])


def get_audit_service(container: Container = Depends(get_container)) -> AuditService:
    return AuditService(container.make_uow())


@router.get("")
async def query_audit(
    principal: Principal = Depends(get_principal),
    service: AuditService = Depends(get_audit_service),
    entity_type: str | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    entries = await service.query(
        principal,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": str(e.id),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id),
            "action": e.action,
            "before": e.before,
            "after": e.after,
            "correlation_id": e.correlation_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
