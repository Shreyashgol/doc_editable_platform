"""FastAPI dependency providers — build request-scoped services from the Container."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...application.security import Principal
from ...application.services.auth_service import AuthService
from ...application.services.document_service import DocumentService
from ...application.services.file_validation import FileValidator
from ...application.services.graph_service import GraphService
from ...application.services.search_service import SearchService
from ...application.services.symbol_service import SymbolService
from ...core.container import Container
from ...core.errors import AuthenticationError
from ...domain.enums import Role

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    container: Container = request.app.state.container
    claims = container.jwt.decode(credentials.credentials, expected_type="access")
    try:
        roles = frozenset(Role(r) for r in claims.get("roles", []))
        return Principal(user_id=UUID(claims["sub"]), roles=roles)
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("malformed token claims") from exc


def get_auth_service(container: Container = Depends(get_container)) -> AuthService:
    return AuthService(container.make_uow(), container.jwt)


def get_document_service(container: Container = Depends(get_container)) -> DocumentService:
    return DocumentService(
        container.make_uow(),
        validator=FileValidator(container.settings),
        object_store=container.object_store,
        virus_scanner=container.virus_scanner,
        settings=container.settings,
    )


def get_symbol_service(container: Container = Depends(get_container)) -> SymbolService:
    return SymbolService(container.make_uow())


def get_graph_service(container: Container = Depends(get_container)) -> GraphService:
    return GraphService(container.make_uow())


def get_search_service(container: Container = Depends(get_container)) -> SearchService:
    return SearchService(container.make_uow(), container.embedder)
