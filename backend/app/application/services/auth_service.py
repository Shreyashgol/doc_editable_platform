"""Authentication use cases: register, authenticate, issue/refresh tokens."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import AuthenticationError, ConflictError
from ...domain.entities import User
from ...domain.enums import Role
from ...infrastructure.security.jwt import JwtService
from ...infrastructure.security.passwords import hash_password, verify_password
from ..unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthService:
    def __init__(self, uow: UnitOfWork, jwt: JwtService) -> None:
        self._uow = uow
        self._jwt = jwt

    async def register(self, email: str, password: str, roles: set[Role] | None = None) -> User:
        async with self._uow:
            if await self._uow.users.get_by_email(email):
                raise ConflictError("a user with this email already exists")
            user = User(
                email=email.lower(),
                password_hash=hash_password(password),
                roles=roles or {Role.ENGINEER},
            )
            await self._uow.users.add(user)
            await self._uow.commit()
            return user

    async def authenticate(self, email: str, password: str) -> TokenPair:
        async with self._uow:
            user = await self._uow.users.get_by_email(email)
            if (
                user is None
                or not user.is_active
                or not verify_password(password, user.password_hash)
            ):
                raise AuthenticationError("invalid credentials")
            roles = [r.value for r in user.roles]
            return TokenPair(
                access_token=self._jwt.issue_access(user.id, roles),
                refresh_token=self._jwt.issue_refresh(user.id, roles),
            )

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = self._jwt.decode(refresh_token, expected_type="refresh")
        roles = claims.get("roles", [])
        sub = claims["sub"]
        from uuid import UUID

        return TokenPair(
            access_token=self._jwt.issue_access(UUID(sub), roles),
            refresh_token=self._jwt.issue_refresh(UUID(sub), roles),
        )
