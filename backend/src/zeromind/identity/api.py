from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

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
    bearer = HTTPBearer(auto_error=False)

    def require_admin(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer),
        ],
    ) -> AdminIdentity:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail={"code": "authentication_required"})
        try:
            return token_service.verify(credentials.credentials)
        except InvalidToken as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_token"},
            ) from error

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
    def me(identity: Annotated[AdminIdentity, Depends(require_admin)]) -> AdminIdentity:
        return identity

    return router

