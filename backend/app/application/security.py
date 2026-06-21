"""Authenticated principal + RBAC helpers used by application services."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ..core.errors import AuthorizationError
from ..domain.enums import Role


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    roles: frozenset[Role]

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles

    def require_role(self, role: Role) -> None:
        if role not in self.roles and not self.is_admin:
            raise AuthorizationError(f"role '{role.value}' required")

    def require_owner_or_admin(self, owner_id: UUID) -> None:
        if owner_id != self.user_id and not self.is_admin:
            raise AuthorizationError("not the owner of this resource")
