from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from ..schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    container = request.app.state.container
    checks: dict[str, str] = {}
    healthy = True
    try:
        async with container.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - failure path
        checks["database"] = f"error: {exc}"
        healthy = False
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=checks)
