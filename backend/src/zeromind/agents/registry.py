import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.agents.domain import AgentDefinition, AgentVersion, ProviderProfile
from zeromind.agents.models import (
    AgentDefinitionModel,
    AgentVersionModel,
    ProviderProfileModel,
)


class DuplicateAgentError(ValueError):
    pass


class AgentRepository(Protocol):
    async def add_provider(self, profile: ProviderProfile) -> None: ...

    async def get_provider(self, profile_id: uuid.UUID) -> ProviderProfile | None: ...

    async def list_providers(self) -> tuple[ProviderProfile, ...]: ...

    async def add_agent(self, definition: AgentDefinition) -> None: ...

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition | None: ...

    async def list_agents(self) -> tuple[AgentDefinition, ...]: ...

    async def append_agent_version(
        self, definition: AgentDefinition, version: AgentVersion
    ) -> None: ...

    async def save_agent_state(self, definition: AgentDefinition) -> None: ...

    async def get_agent_version(
        self, agent_id: uuid.UUID, version: int
    ) -> AgentVersion | None: ...

    async def list_agent_versions(
        self, agent_id: uuid.UUID
    ) -> tuple[AgentVersion, ...]: ...


class InMemoryAgentRepository:
    def __init__(self) -> None:
        self._providers: dict[uuid.UUID, ProviderProfile] = {}
        self._provider_names: set[str] = set()
        self._agents: dict[uuid.UUID, AgentDefinition] = {}
        self._agent_names: set[str] = set()
        self._versions: dict[uuid.UUID, dict[int, AgentVersion]] = {}

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
        self._versions[definition.id] = {1: definition.current_version()}

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    async def list_agents(self) -> tuple[AgentDefinition, ...]:
        return tuple(sorted(self._agents.values(), key=lambda item: item.name))

    async def append_agent_version(
        self, definition: AgentDefinition, version: AgentVersion
    ) -> None:
        versions = self._versions.get(definition.id)
        if versions is None:
            raise KeyError(definition.id)
        if version.version in versions:
            raise ValueError("agent version already exists")
        versions[version.version] = version
        self._agents[definition.id] = definition

    async def save_agent_state(self, definition: AgentDefinition) -> None:
        if definition.id not in self._agents:
            raise KeyError(definition.id)
        self._agents[definition.id] = definition

    async def get_agent_version(
        self, agent_id: uuid.UUID, version: int
    ) -> AgentVersion | None:
        return self._versions.get(agent_id, {}).get(version)

    async def list_agent_versions(
        self, agent_id: uuid.UUID
    ) -> tuple[AgentVersion, ...]:
        return tuple(
            item
            for _, item in sorted(self._versions.get(agent_id, {}).items())
        )


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

    async def get_agent_version(
        self, agent_id: uuid.UUID, version: int
    ) -> AgentVersion:
        value = await self._repository.get_agent_version(agent_id, version)
        if value is None:
            raise KeyError((agent_id, version))
        return value

    async def list_agent_versions(
        self, agent_id: uuid.UUID
    ) -> tuple[AgentVersion, ...]:
        if await self._repository.get_agent(agent_id) is None:
            raise KeyError(agent_id)
        return await self._repository.list_agent_versions(agent_id)

    async def update_agent(
        self,
        agent_id: uuid.UUID,
        *,
        system_prompt: str,
        capabilities: tuple[str, ...],
        provider_profile_id: uuid.UUID | None = None,
        input_schema: dict[str, object] | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> AgentDefinition:
        definition = await self.get_agent(agent_id)
        target_provider_id = provider_profile_id or definition.provider_profile_id
        if await self._repository.get_provider(target_provider_id) is None:
            raise ValueError("provider profile does not exist")
        version = definition.update(
            system_prompt=system_prompt,
            capabilities=capabilities,
            provider_profile_id=target_provider_id,
            input_schema=(definition.input_schema if input_schema is None else input_schema),
            output_schema=(
                definition.output_schema if output_schema is None else output_schema
            ),
        )
        await self._repository.append_agent_version(definition, version)
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
        await self._repository.save_agent_state(definition)
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


def _version_domain(model: AgentVersionModel) -> AgentVersion:
    return AgentVersion(
        id=model.id,
        agent_id=model.agent_id,
        version=model.version,
        capabilities=tuple(model.capabilities),
        system_prompt=model.system_prompt,
        provider_profile_id=model.provider_profile_id,
        input_schema=model.input_schema,
        output_schema=model.output_schema,
        created_at=_as_utc(model.created_at),
    )


def _agent_domain(model: AgentDefinitionModel, version: AgentVersionModel) -> AgentDefinition:
    return AgentDefinition(
        id=model.id,
        name=model.name,
        description=model.description,
        capabilities=tuple(version.capabilities),
        system_prompt=version.system_prompt,
        provider_profile_id=version.provider_profile_id,
        input_schema=version.input_schema,
        output_schema=version.output_schema,
        enabled=model.enabled,
        version=version.version,
        version_id=version.id,
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
                    enabled=definition.enabled,
                    current_version=definition.version,
                    created_at=definition.created_at,
                    updated_at=definition.updated_at,
                )
            )
            session.add(self._version_model(definition.current_version()))
            try:
                await session.flush()
            except IntegrityError as error:
                raise DuplicateAgentError(definition.name) from error

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDefinition | None:
        async with self._sessions() as session:
            model = await session.get(AgentDefinitionModel, agent_id)
            if model is None:
                return None
            version = await self._current_version_model(session, model)
            return _agent_domain(model, version)

    async def list_agents(self) -> tuple[AgentDefinition, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(AgentDefinitionModel).order_by(AgentDefinitionModel.name)
            )
            result: list[AgentDefinition] = []
            for model in models:
                result.append(
                    _agent_domain(
                        model,
                        await self._current_version_model(session, model),
                    )
                )
            return tuple(result)

    async def append_agent_version(
        self, definition: AgentDefinition, version: AgentVersion
    ) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(AgentDefinitionModel, definition.id)
            if model is None:
                raise KeyError(definition.id)
            session.add(self._version_model(version))
            model.current_version = version.version
            model.updated_at = definition.updated_at
            try:
                await session.flush()
            except IntegrityError as error:
                raise ValueError("agent version already exists") from error

    async def save_agent_state(self, definition: AgentDefinition) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(AgentDefinitionModel, definition.id)
            if model is None:
                raise KeyError(definition.id)
            model.enabled = definition.enabled
            model.updated_at = definition.updated_at

    async def get_agent_version(
        self, agent_id: uuid.UUID, version: int
    ) -> AgentVersion | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(AgentVersionModel).where(
                    AgentVersionModel.agent_id == agent_id,
                    AgentVersionModel.version == version,
                )
            )
            return _version_domain(model) if model else None

    async def list_agent_versions(
        self, agent_id: uuid.UUID
    ) -> tuple[AgentVersion, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(AgentVersionModel)
                .where(AgentVersionModel.agent_id == agent_id)
                .order_by(AgentVersionModel.version)
            )
            return tuple(_version_domain(model) for model in models)

    @staticmethod
    def _version_model(version: AgentVersion) -> AgentVersionModel:
        return AgentVersionModel(
            id=version.id,
            agent_id=version.agent_id,
            version=version.version,
            capabilities=list(version.capabilities),
            system_prompt=version.system_prompt,
            provider_profile_id=version.provider_profile_id,
            input_schema=version.input_schema,
            output_schema=version.output_schema,
            created_at=version.created_at,
        )

    @staticmethod
    async def _current_version_model(
        session: AsyncSession, model: AgentDefinitionModel
    ) -> AgentVersionModel:
        version = await session.scalar(
            select(AgentVersionModel).where(
                AgentVersionModel.agent_id == model.id,
                AgentVersionModel.version == model.current_version,
            )
        )
        if version is None:
            raise RuntimeError("agent current version is missing")
        return version
