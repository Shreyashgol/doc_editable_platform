"""Composition root.

The single place where concrete adapters are chosen and wired to the ports. Swapping an
implementation (e.g. InMemoryObjectStore → S3, NullVirusScanner → ClamAV) happens here and
nowhere else. Tests build a Container with fakes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..application.unit_of_work import UnitOfWork
from ..domain.ports import Embedder, ObjectStore, VirusScanner
from ..infrastructure.db.base import create_engine_and_sessionmaker
from ..infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from ..infrastructure.factories import build_embedder
from ..infrastructure.security.clamav import ClamAVScanner, NullVirusScanner
from ..infrastructure.security.jwt import JwtService
from ..infrastructure.storage.s3 import InMemoryObjectStore, S3ObjectStore
from .config import Settings


class Container:
    def __init__(
        self,
        settings: Settings,
        *,
        object_store: ObjectStore | None = None,
        virus_scanner: VirusScanner | None = None,
        embedder: Embedder | None = None,
        engine: AsyncEngine | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.settings = settings
        if engine is not None and session_factory is not None:
            self.engine, self.session_factory = engine, session_factory
        else:
            self.engine, self.session_factory = create_engine_and_sessionmaker(settings)
        self.jwt = JwtService(settings)
        self.object_store: ObjectStore = object_store or self._default_object_store(settings)
        self.virus_scanner: VirusScanner = virus_scanner or self._default_scanner(settings)
        # Must match the worker's embedder so query vectors share the stored vectors' space.
        self.embedder: Embedder = embedder or build_embedder(settings)

    @staticmethod
    def _default_object_store(settings: Settings) -> ObjectStore:
        if settings.environment == "test" or settings.s3_endpoint_url is None:
            return InMemoryObjectStore()
        return S3ObjectStore(settings)

    @staticmethod
    def _default_scanner(settings: Settings) -> VirusScanner:
        if not settings.clamav_enabled:
            return NullVirusScanner()
        return ClamAVScanner(settings.clamav_host, settings.clamav_port)

    def make_uow(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory, self.settings)

    async def dispose(self) -> None:
        await self.engine.dispose()
