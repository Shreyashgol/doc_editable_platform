from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.entities import User
from ...domain.ports import UserRepository
from ..db import mappers
from ..db.models import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.lower())
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.user_to_domain(row) if row else None

    async def get(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return mappers.user_to_domain(row) if row else None

    async def add(self, user: User) -> User:
        user.email = user.email.lower()
        self._session.add(mappers.user_to_row(user))
        await self._session.flush()
        return user
