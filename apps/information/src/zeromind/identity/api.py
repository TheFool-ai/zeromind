from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from zeromind.identity.context import request_identity
from zeromind.identity.tokens import AdminIdentity, InvalidToken, TokenService


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class IdentityResponse(BaseModel):
    username: str
    role: str


def create_identity_router(token_service: TokenService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["identity"])

    @router.post("/token", response_model=TokenResponse)
    def login(request: LoginRequest) -> TokenResponse:
        try:
            token = token_service.authenticate(request.username, request.password)
        except InvalidToken as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_credentials"},
            ) from error
        return TokenResponse(access_token=token)

    @router.get("/me", response_model=IdentityResponse)
    def me(request: Request) -> AdminIdentity:
        return request_identity(request)

    return router
