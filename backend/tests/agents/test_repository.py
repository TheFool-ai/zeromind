from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.models import AgentDefinitionModel, ProviderProfileModel
from zeromind.agents.registry import AgentRegistry, SqlAlchemyAgentRepository


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ProviderProfileModel.__table__.create)
        await connection.run_sync(AgentDefinitionModel.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_supports_registration_and_discovery(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    registry = AgentRegistry(SqlAlchemyAgentRepository(sessions))
    profile = ProviderProfile.create(
        name="default",
        provider="openai",
        model="gpt-5-mini",
        api_key_env="OPENAI_API_KEY",
        identifier=UUID("33333333-3333-3333-3333-333333333333"),
    )
    await registry.register_provider(profile)
    await registry.register_agent(
        AgentDefinition.create(
            name="summarizer",
            description="Summarizes",
            capabilities=("summarize", "zh"),
            system_prompt="Return JSON.",
            provider_profile_id=profile.id,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
    )

    discovered = await registry.discover(("summarize", "zh"))

    assert [item.name for item in discovered] == ["summarizer"]
    assert (await registry.get_provider(profile.id)).api_key_env == "OPENAI_API_KEY"
