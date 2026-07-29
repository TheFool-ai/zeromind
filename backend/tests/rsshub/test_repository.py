from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.rsshub.domain import DuplicateRSSHubInstanceError, RSSHubInstance
from zeromind.rsshub.models import RSSHubInstanceModel
from zeromind.rsshub.repository import SqlAlchemyRSSHubInstanceRepository


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(RSSHubInstanceModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_persists_encrypted_access_key(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyRSSHubInstanceRepository(sessions)
    instance = RSSHubInstance.create(
        name="Primary",
        base_url="https://rsshub.example.com",
        encrypted_access_key="encrypted-value",
        active=True,
    )

    await repository.add(instance)
    loaded = await repository.get(instance.id)

    assert loaded == instance
    assert loaded is not None
    assert loaded.encrypted_access_key == "encrypted-value"


@pytest.mark.asyncio
async def test_repository_rejects_duplicate_base_url(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyRSSHubInstanceRepository(sessions)
    await repository.add(
        RSSHubInstance.create(name="Primary", base_url="https://rsshub.example.com")
    )

    with pytest.raises(DuplicateRSSHubInstanceError):
        await repository.add(
            RSSHubInstance.create(
                name="Duplicate",
                base_url="HTTPS://RSSHUB.EXAMPLE.COM:443/",
            )
        )


@pytest.mark.asyncio
async def test_repository_activation_replaces_previous_active_instance(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyRSSHubInstanceRepository(sessions)
    first = RSSHubInstance.create(
        name="Primary",
        base_url="https://rsshub.example.com",
        active=True,
    )
    second = RSSHubInstance.create(
        name="Backup",
        base_url="https://backup.example.com",
    )
    await repository.add(first)
    await repository.add(second)

    await repository.activate(second.id)

    assert (await repository.get(first.id)).active is False  # type: ignore[union-attr]
    assert (await repository.get(second.id)).active is True  # type: ignore[union-attr]
