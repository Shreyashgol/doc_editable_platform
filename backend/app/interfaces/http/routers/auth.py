from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ....application.services.auth_service import AuthService
from ..deps import get_auth_service
from ..schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, service: AuthService = Depends(get_auth_service)
) -> UserResponse:
    user = await service.register(body.email, body.password)
    return UserResponse(id=str(user.id), email=user.email, roles=[r.value for r in user.roles])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    tokens = await service.authenticate(body.email, body.password)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    tokens = await service.refresh(body.refresh_token)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)
