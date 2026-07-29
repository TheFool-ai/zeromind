import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True)
class WebhookEndpoint:
    id: uuid.UUID
    name: str
    url: str
    secret_env: str
    events: tuple[str, ...]
    enabled: bool
    max_attempts: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        name: str,
        url: str,
        secret_env: str,
        events: tuple[str, ...],
        max_attempts: int = 3,
        identifier: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> "WebhookEndpoint":
        if not name.strip() or not secret_env.strip() or not events:
            raise ValueError("webhook name, secret environment key, and events are required")
        if not 1 <= max_attempts <= 5:
            raise ValueError("webhook max_attempts must be between 1 and 5")
        current = now or datetime.now(UTC)
        return cls(
            id=identifier or uuid.uuid4(),
            name=name.strip(),
            url=url.strip(),
            secret_env=secret_env.strip(),
            events=tuple(dict.fromkeys(events)),
            enabled=True,
            max_attempts=max_attempts,
            created_at=current,
            updated_at=current,
        )


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    endpoint_id: uuid.UUID
    event_id: str
    status: str
    attempts: int
    response_status: int | None
    error: str | None

