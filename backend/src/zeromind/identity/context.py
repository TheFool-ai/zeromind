from fastapi import HTTPException, Request, status

from zeromind.identity.tokens import AdminIdentity


def request_identity(request: Request) -> AdminIdentity:
    identity = getattr(request.state, "identity", None)
    if not isinstance(identity, AdminIdentity):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        )
    return identity
