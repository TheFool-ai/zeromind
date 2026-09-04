import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.rsshub.domain import (
    DuplicateRSSHubInstanceError,
    RSSHubAuthenticationMode,
    RSSHubInstance,
)
from zeromind.rsshub.models import RSSHubInstanceModel


class RSSHubInstanceRepository(Protocol):
    async def add(self, instance: RSSHubInstance) -> None: ...

    async def get(self, instance_id: uuid.UUID) -> RSSHubInstance | None: ...

    async def list(self) -> tuple[RSSHubInstance, ...]: ...

    async def get_active(self) -> RSSHubInstance | None: ...

    async def save(self, instance: RSSHubInstance) -> None: ...

    async def activate(self, instance_id: uuid.UUID) -> None: ...

    async def delete(self, instance_id: uuid.UUID) -> None: ...


class InMemoryRSSHubInstanceRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, RSSHubInstance] = {}

    def _duplicate(self, instance: RSSHubInstance) -> bool:
        return any(
            item.id != instance.id
            and (item.name == instance.name or item.base_url == instance.base_url)
            for item in self._items.values()
        )

    async def add(self, instance: RSSHubInstance) -> None:
        if self._duplicate(instance):
            raise DuplicateRSSHubInstanceError(instance.name)
        if instance.active and any(item.active for item in self._items.values()):
            raise DuplicateRSSHubInstanceError("an active RSSHub instance already exists")
        self._items[instance.id] = replace(instance)

    async def get(self, instance_id: uuid.UUID) -> RSSHubInstance | None:
        instance = self._items.get(instance_id)
        return replace(instance) if instance else None

    async def list(self) -> tuple[RSSHubInstance, ...]:
        return tuple(
            replace(item)
            for item in sorted(self._items.values(), key=lambda value: value.name)
        )

    async def get_active(self) -> RSSHubInstance | None:
        instance = next((item for item in self._items.values() if item.active), None)
        return replace(instance) if instance else None

    async def save(self, instance: RSSHubInstance) -> None:
        if instance.id not in self._items:
            raise KeyError(instance.id)
        if self._duplicate(instance):
            raise DuplicateRSSHubInstanceError(instance.name)
        self._items[instance.id] = replace(instance)

    async def activate(self, instance_id: uuid.UUID) -> None:
        if instance_id not in self._items:
            raise KeyError(instance_id)
        for identifier, item in tuple(self._items.items()):
            self._items[identifier] = replace(item, active=identifier == instance_id)

    async def delete(self, instance_id: uuid.UUID) -> None:
        if self._items.pop(instance_id, None) is None:
            raise KeyError(instance_id)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_domain(model: RSSHubInstanceModel) -> RSSHubInstance:
    return RSSHubInstance(
        id=model.id,
        name=model.name,
        base_url=model.base_url,
        encrypted_access_key=model.encrypted_access_key,
        authentication_mode=RSSHubAuthenticationMode(model.authentication_mode),
        enabled=model.enabled,
        active=model.active,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _to_model(instance: RSSHubInstance) -> RSSHubInstanceModel:
    return RSSHubInstanceModel(
        id=instance.id,
        name=instance.name,
        base_url=instance.base_url,
        encrypted_access_key=instance.encrypted_access_key,
        authentication_mode=instance.authentication_mode.value,
        enabled=instance.enabled,
        active=instance.active,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


class SqlAlchemyRSSHubInstanceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, instance: RSSHubInstance) -> None:
        async with self._sessions() as session, session.begin():
            session.add(_to_model(instance))
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateRSSHubInstanceError(instance.name) from error

    async def get(self, instance_id: uuid.UUID) -> RSSHubInstance | None:
        async with self._sessions() as session:
            model = await session.get(RSSHubInstanceModel, instance_id)
            return _to_domain(model) if model else None

    async def list(self) -> tuple[RSSHubInstance, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(RSSHubInstanceModel).order_by(RSSHubInstanceModel.name)
            )
            return tuple(_to_domain(model) for model in models)

    async def get_active(self) -> RSSHubInstance | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(RSSHubInstanceModel).where(RSSHubInstanceModel.active.is_(True))
            )
            return _to_domain(model) if model else None

    async def save(self, instance: RSSHubInstance) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(RSSHubInstanceModel, instance.id)
            if model is None:
                raise KeyError(instance.id)
            model.name = instance.name
            model.base_url = instance.base_url
            model.encrypted_access_key = instance.encrypted_access_key
            model.authentication_mode = instance.authentication_mode.value
            model.enabled = instance.enabled
            model.active = instance.active
            model.updated_at = instance.updated_at
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateRSSHubInstanceError(instance.name) from error

    async def activate(self, instance_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(RSSHubInstanceModel, instance_id)
            if model is None:
                raise KeyError(instance_id)
            await session.execute(
                update(RSSHubInstanceModel)
                .where(RSSHubInstanceModel.active.is_(True))
                .values(active=False)
            )
            model.active = True

    async def delete(self, instance_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(RSSHubInstanceModel, instance_id)
            if model is None:
                raise KeyError(instance_id)
            await session.delete(model)
