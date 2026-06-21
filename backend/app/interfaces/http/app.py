"""FastAPI application factory.

Thin: it wires the Container, middleware, exception handlers, and routers. No business logic.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ...core.config import Settings, get_settings
from ...core.container import Container
from ...core.logging import configure_logging
from .metrics import register_metrics
from .middleware import register_exception_handlers, register_middleware
from .routers import auth, documents, graph, health, search, symbols


def create_app(*, settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        app.state.container = container or Container(settings)
        yield
        await app.state.container.dispose()

    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    register_metrics(app)
    register_middleware(app, settings)
    register_exception_handlers(app)

    prefix = settings.api_v1_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(symbols.documents_router, prefix=prefix)
    app.include_router(symbols.router, prefix=prefix)
    app.include_router(graph.documents_router, prefix=prefix)
    app.include_router(graph.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(health.router)
    return app
