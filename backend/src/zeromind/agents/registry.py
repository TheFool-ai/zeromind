import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.agents.domain import AgentDefinition, ProviderProfile
from zeromind.agents.models import AgentDefinitionModel, ProviderProfileModel


class DuplicateAgentError(ValueError):
    pass


class AgentRepository(Protocol):
    async def add_provider(self, profile: ProviderProfile) -> None: ...

    async def get_provider(self, profile_id: uuid.UUID) -> ProviderProfile | None: ...

    async def list_providers(self) -> tuple[ProviderProfile, ...]: ...

    async def add_agent(self, definition: AgentDefinition) -> None: ...

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition | None: ...

    async def list_agents(self) -> tuple[AgentDefinition, ...]: ...

    async def save_agent(self, definition: AgentDefinition) -> None: ...


class InMemoryAgentRepository:
    def __init__(self) -> None:
        self._providers: dict[uuid.UUID, ProviderProfile] = {}
        self._provider_names: set[str] = set()
        self._agents: dict[uuid.UUID, AgentDefinition] = {}
        self._agent_names: set[str] = set()

    async def add_provider(self, profile: ProviderProfile) -> None:
        if profile.name in self._provider_names:
            raise DuplicateAgentError(profile.name)
        self._providers[profile.id] = profile
        self._provider_names.add(profile.name)

    async def get_provider(self, profile_id: uuid.UUID) -> ProviderProfile | None:
        return self._providers.get(profile_id)

    async def list_providers(self) -> tuple[ProviderProfile, ...]:
        return tuple(sorted(self._providers.values(), key=lambda item: item.name))

    async def add_agent(self, definition: AgentDefinition) -> None:
        if definition.name in self._agent_names:
            raise DuplicateAgentError(definition.name)
        self._agents[definition.id] = definition
        self._agent_names.add(definition.name)

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    async def list_agents(self) -> tuple[AgentDefinition, ...]:
        return tuple(sorted(self._agents.values(), key=lambda item: item.name))

    async def save_agent(self, definition: AgentDefinition) -> None:
        if definition.id not in self._agents:
            raise KeyError(definition.id)
        self._agents[definition.id] = definition


class AgentRegistry:
    def __init__(self, repository: AgentRepository) -> None:
        self._repository = repository

    async def register_provider(self, profile: ProviderProfile) -> None:
        await self._repository.add_provider(profile)

    async def register_agent(self, definition: AgentDefinition) -> None:
        if await self._repository.get_provider(definition.provider_profile_id) is None:
            raise ValueError("provider profile does not exist")
        await self._repository.add_agent(definition)

    async def get_provider(self, profile_id: uuid.UUID) -> ProviderProfile:
        profile = await self._repository.get_provider(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        return profile

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition:
        definition = await self._repository.get_agent(agent_id)
        if definition is None:
            raise KeyError(agent_id)
        return definition

    async def list_providers(self) -> tuple[ProviderProfile, ...]:
        return await self._repository.list_providers()

    async def list_agents(self) -> tuple[AgentDefinition, ...]:
        return await self._repository.list_agents()

    async def update_agent(
        self,
        agent_id: uuid.UUID,
        *,
        system_prompt: str,
        capabilities: tuple[str, ...],
    ) -> AgentDefinition:
        definition = await self.get_agent(agent_id)
        definition.update(
            system_prompt=system_prompt,
            capabilities=capabilities,
        )
        await self._repository.save_agent(definition)
        return definition

    async def set_agent_enabled(
        self,
        agent_id: uuid.UUID,
        *,
        enabled: bool,
    ) -> AgentDefinition:
        definition = await self.get_agent(agent_id)
        if enabled:
            definition.enable()
        else:
            definition.disable()
        await self._repository.save_agent(definition)
        return definition

    async def discover(
        self,
        capabilities: tuple[str, ...],
    ) -> tuple[AgentDefinition, ...]:
        required = {value.strip().lower() for value in capabilities if value.strip()}
        agents = await self._repository.list_agents()
        return tuple(
            agent
            for agent in agents
            if agent.enabled and required.issubset(agent.capabilities)
        )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _provider_domain(model: ProviderProfileModel) -> ProviderProfile:
    return ProviderProfile(
        id=model.id,
        name=model.name,
        provider=model.provider,
        model=model.model,
        api_key_env=model.api_key_env,
        thinking_level=model.thinking_level,
        parameters=model.parameters,
        enabled=model.enabled,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _agent_domain(model: AgentDefinitionModel) -> AgentDefinition:
    return AgentDefinition(
        id=model.id,
        name=model.name,
        description=model.description,
        capabilities=tuple(model.capabilities),
        system_prompt=model.system_prompt,
        provider_profile_id=model.provider_profile_id,
        input_schema=model.input_schema,
        output_schema=model.output_schema,
        enabled=model.enabled,
        version=model.version,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class SqlAlchemyAgentRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_provider(self, profile: ProviderProfile) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                ProviderProfileModel(
                    id=profile.id,
                    name=profile.name,
                    provider=profile.provider,
                    model=profile.model,
                    api_key_env=profile.api_key_env,
                    thinking_level=profile.thinking_level,
                    parameters=profile.parameters,
                    enabled=profile.enabled,
                    created_at=profile.created_at,
                    updated_at=profile.updated_at,
                )
            )
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateAgentError(profile.name) from error

    async def get_provider(self, profile_id: uuid.UUID) -> ProviderProfile | None:
        async with self._sessions() as session:
            model = await session.get(ProviderProfileModel, profile_id)
            return _provider_domain(model) if model else None

    async def list_providers(self) -> tuple[ProviderProfile, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(ProviderProfileModel).order_by(ProviderProfileModel.name)
            )
            return tuple(_provider_domain(model) for model in models)

    async def add_agent(self, definition: AgentDefinition) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                AgentDefinitionModel(
                    id=definition.id,
                    name=definition.name,
                    description=definition.description,
                    capabilities=list(definition.capabilities),
                    system_prompt=definition.system_prompt,
                    provider_profile_id=definition.provider_profile_id,
                    input_schema=definition.input_schema,
                    output_schema=definition.output_schema,
                    enabled=definition.enabled,
                    version=definition.version,
                    created_at=definition.created_at,
                    updated_at=definition.updated_at,
                )
            )
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateAgentError(definition.name) from error

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition | None:
        async with self._sessions() as session:
            model = await session.get(AgentDefinitionModel, agent_id)
            return _agent_domain(model) if model else None

    async def list_agents(self) -> tuple[AgentDefinition, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(AgentDefinitionModel).order_by(AgentDefinitionModel.name)
            )
            return tuple(_agent_domain(model) for model in models)

    async def save_agent(self, definition: AgentDefinition) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(AgentDefinitionModel, definition.id)
            if model is None:
                raise KeyError(definition.id)
            model.name = definition.name
            model.description = definition.description
            model.capabilities = list(definition.capabilities)
            model.system_prompt = definition.system_prompt
            model.provider_profile_id = definition.provider_profile_id
            model.input_schema = definition.input_schema
            model.output_schema = definition.output_schema
            model.enabled = definition.enabled
            model.version = definition.version
            model.updated_at = definition.updated_at
