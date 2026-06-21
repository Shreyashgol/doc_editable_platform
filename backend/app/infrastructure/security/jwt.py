"""JWT issue/verify for access and refresh tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt

from ...core.config import Settings
from ...core.errors import AuthenticationError


class JwtService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret
        self._alg = settings.jwt_algorithm
        self._access_ttl = settings.access_token_ttl_seconds
        self._refresh_ttl = settings.refresh_token_ttl_seconds

    def _encode(self, sub: UUID, roles: list[str], ttl: int, token_type: str) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(sub),
            "roles": roles,
            "type": token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        }
        return jwt.encode(claims, self._secret, algorithm=self._alg)

    def issue_access(self, sub: UUID, roles: list[str]) -> str:
        return self._encode(sub, roles, self._access_ttl, "access")

    def issue_refresh(self, sub: UUID, roles: list[str]) -> str:
        return self._encode(sub, roles, self._refresh_ttl, "refresh")

    def decode(self, token: str, *, expected_type: str = "access") -> dict:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[self._alg])
        except JWTError as exc:
            raise AuthenticationError("invalid or expired token") from exc
        if claims.get("type") != expected_type:
            raise AuthenticationError(f"expected {expected_type} token")
        return claims
