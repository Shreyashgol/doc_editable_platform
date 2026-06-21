"""Worker entrypoint: ``python -m app.interfaces.worker.run``."""

from __future__ import annotations

import asyncio

from ...core.config import get_settings
from ...core.logging import configure_logging
from ...infrastructure.db.base import create_engine_and_sessionmaker
from .engines import build_engines
from .runner import PipelineRunner


async def _main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json=settings.log_json)
    _engine, session_factory = create_engine_and_sessionmaker(settings)
    engines = build_engines(settings)
    runner = PipelineRunner(session_factory, settings, engines)
    await runner.run_forever()


def main() -> None:  # pragma: no cover
    asyncio.run(_main())


if __name__ == "__main__":  # pragma: no cover
    main()
