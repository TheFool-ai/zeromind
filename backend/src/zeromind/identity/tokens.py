import hmac
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from zeromind.shared.config import Settings


class InvalidToken(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    username: str
    role: str = "admin"


class TokenService:
    def __init__(self, settings: Settings, *, max_age_seconds: int = 8 * 60 * 60) -> None:
        self._username = settings.admin_username
        self._password = settings.admin_password
        self._serializer = URLSafeTimedSerializer(
            settings.token_secret,
            salt="zeromind-admin",
        )
        self._max_age = max_age_seconds

    def authenticate(self, username: str, password: str) -> str:
        if not (
            hmac.compare_digest(username, self._username)
            and hmac.compare_digest(password, self._password)
        ):
            raise InvalidToken("invalid administrator credentials")
        return self._serializer.dumps({"sub": self._username, "role": "admin"})

    def verify(self, token: str) -> AdminIdentity:
        try:
            payload = self._serializer.loads(token, max_age=self._max_age)
        except (BadSignature, SignatureExpired) as error:
            raise InvalidToken("invalid or expired token") from error
        if not isinstance(payload, dict) or payload.get("sub") != self._username:
            raise InvalidToken("invalid token subject")
        return AdminIdentity(username=self._username)

