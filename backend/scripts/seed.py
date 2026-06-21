"""Create an initial admin user. Run: ``python -m scripts.seed`` (env must point at the DB)."""

from __future__ import annotations

import asyncio
import os

from app.core.config import get_settings
from app.domain.entities import User
from app.domain.enums import Role
from app.infrastructure.db.base import create_engine_and_sessionmaker
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.passwords import hash_password


async def main() -> None:
    email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("SEED_ADMIN_PASSWORD", "changeme-admin-1")
    settings = get_settings()
    engine, sf = create_engine_and_sessionmaker(settings)
    uow = SqlAlchemyUnitOfWork(sf, settings)
    async with uow:
        if await uow.users.get_by_email(email):
            print(f"admin {email} already exists")
        else:
            await uow.users.add(
                User(email=email, password_hash=hash_password(password), roles={Role.ADMIN})
            )
            await uow.commit()
            print(f"created admin {email}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
