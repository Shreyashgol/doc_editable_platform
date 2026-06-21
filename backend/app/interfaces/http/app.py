"""FastAPI application factory.

Thin: it wires the Container, middleware, exception handlers, and routers. No business logic.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ...core.config import Settings, get_settings
from ...core.container import Container
from ...core.logging import configure_logging, get_logger
from .metrics import register_metrics
from .middleware import register_exception_handlers, register_middleware
from .routers import audit, auth, documents, graph, health, search, symbols

_log = get_logger("app")


async def _run_in_process_worker(container: Container) -> None:
    """Drive the pipeline loop inside the API process (APP_RUN_WORKER_IN_PROCESS=true).

    Resilient: a crash in the loop is logged and restarted after a short delay so a transient
    DB hiccup never takes the embedded worker down for good.
    """
    from ..worker.engines import build_engines
    from ..worker.runner import PipelineRunner

    engines = build_engines(container.settings, object_store=container.object_store)
    runner = PipelineRunner(container.session_factory, container.settings, engines)
    _log.info("in_process_worker_starting")
    while True:
        try:
            await runner.run_forever()
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _log.exception("in_process_worker_crashed", error=str(exc))
            await asyncio.sleep(5)


def create_app(*, settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        app.state.container = container or Container(settings)
        worker_task: asyncio.Task | None = None
        if settings.run_worker_in_process:
            worker_task = asyncio.create_task(_run_in_process_worker(app.state.container))
        try:
            yield
        finally:
            if worker_task is not None:
                worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker_task
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
    # CORS added last → outermost, so preflight OPTIONS is handled before other middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    prefix = settings.api_v1_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(symbols.documents_router, prefix=prefix)
    app.include_router(symbols.router, prefix=prefix)
    app.include_router(graph.documents_router, prefix=prefix)
    app.include_router(graph.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)
    app.include_router(health.router)
    return app
