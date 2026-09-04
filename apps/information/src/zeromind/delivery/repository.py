import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.delivery.domain import WebhookEndpoint
from zeromind.delivery.models import WebhookEndpointModel


class WebhookRepository(Protocol):
    async def add(self, endpoint: WebhookEndpoint) -> None: ...

    async def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint | None: ...

    async def list(self) -> tuple[WebhookEndpoint, ...]: ...

    async def save(self, endpoint: WebhookEndpoint) -> None: ...


class InMemoryWebhookRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, WebhookEndpoint] = {}

    async def add(self, endpoint: WebhookEndpoint) -> None:
        if any(item.name == endpoint.name for item in self._items.values()):
            raise ValueError("duplicate webhook name")
        self._items[endpoint.id] = endpoint

    async def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint | None:
        return self._items.get(endpoint_id)

    async def list(self) -> tuple[WebhookEndpoint, ...]:
        return tuple(sorted(self._items.values(), key=lambda item: item.name))

    async def save(self, endpoint: WebhookEndpoint) -> None:
        if endpoint.id not in self._items:
            raise KeyError(endpoint.id)
        self._items[endpoint.id] = endpoint


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _domain(model: WebhookEndpointModel) -> WebhookEndpoint:
    return WebhookEndpoint(
        id=model.id,
        name=model.name,
        url=model.url,
        secret_env=model.secret_env,
        events=tuple(model.events),
        enabled=model.enabled,
        max_attempts=model.max_attempts,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class SqlAlchemyWebhookRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, endpoint: WebhookEndpoint) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                WebhookEndpointModel(
                    id=endpoint.id,
                    name=endpoint.name,
                    url=endpoint.url,
                    secret_env=endpoint.secret_env,
                    events=list(endpoint.events),
                    enabled=endpoint.enabled,
                    max_attempts=endpoint.max_attempts,
                    created_at=endpoint.created_at,
                    updated_at=endpoint.updated_at,
                )
            )
            try:
                await session.flush()
            except IntegrityError as error:
                raise ValueError("duplicate webhook name") from error

    async def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint | None:
        async with self._sessions() as session:
            model = await session.get(WebhookEndpointModel, endpoint_id)
            return _domain(model) if model else None

    async def list(self) -> tuple[WebhookEndpoint, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(WebhookEndpointModel).order_by(WebhookEndpointModel.name)
            )
            return tuple(_domain(model) for model in models)

    async def save(self, endpoint: WebhookEndpoint) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(WebhookEndpointModel, endpoint.id)
            if model is None:
                raise KeyError(endpoint.id)
            model.name = endpoint.name
            model.url = endpoint.url
            model.secret_env = endpoint.secret_env
            model.events = list(endpoint.events)
            model.enabled = endpoint.enabled
            model.max_attempts = endpoint.max_attempts
            model.updated_at = endpoint.updated_at

