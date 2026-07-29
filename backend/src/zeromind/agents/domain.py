import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

THINKING_LEVELS = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(slots=True)
class ProviderProfile:
    id: uuid.UUID
    name: str
    provider: str
    model: str
    api_key_env: str = field(repr=False)
    thinking_level: str
    parameters: dict[str, object]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        name: str,
        provider: str,
        model: str,
        api_key_env: str,
        thinking_level: str = "off",
        parameters: dict[str, object] | None = None,
        identifier: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> "ProviderProfile":
        current = now or datetime.now(UTC)
        if thinking_level not in THINKING_LEVELS:
            raise ValueError("unsupported thinking level")
        if not ENV_NAME.fullmatch(api_key_env):
            raise ValueError("api_key_env must be an environment variable name")
        if not name.strip() or not provider.strip() or not model.strip():
            raise ValueError("name, provider, and model are required")
        return cls(
            id=identifier or uuid.uuid4(),
            name=name.strip(),
            provider=provider.strip(),
            model=model.strip(),
            api_key_env=api_key_env,
            thinking_level=thinking_level,
            parameters=dict(parameters or {}),
            enabled=True,
            created_at=current,
            updated_at=current,
        )

    def resolve_api_key(self) -> str:
        value = os.getenv(self.api_key_env)
        if not value:
            raise ValueError(f"provider credential {self.api_key_env} is not configured")
        return value


@dataclass(slots=True)
class AgentDefinition:
    id: uuid.UUID
    name: str
    description: str
    capabilities: tuple[str, ...]
    system_prompt: str
    provider_profile_id: uuid.UUID
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        name: str,
        description: str,
        capabilities: tuple[str, ...],
        system_prompt: str,
        provider_profile_id: uuid.UUID,
        input_schema: dict[str, object],
        output_schema: dict[str, object],
        identifier: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> "AgentDefinition":
        current = now or datetime.now(UTC)
        if not name.strip() or not system_prompt.strip():
            raise ValueError("agent name and system prompt are required")
        normalized_capabilities = tuple(
            sorted({value.strip().lower() for value in capabilities if value.strip()})
        )
        return cls(
            id=identifier or uuid.uuid4(),
            name=name.strip(),
            description=description.strip(),
            capabilities=normalized_capabilities,
            system_prompt=system_prompt.strip(),
            provider_profile_id=provider_profile_id,
            input_schema=dict(input_schema),
            output_schema=dict(output_schema),
            enabled=True,
            version=1,
            created_at=current,
            updated_at=current,
        )

    def disable(self, *, now: datetime | None = None) -> None:
        self.enabled = False
        self.updated_at = now or datetime.now(UTC)

    def enable(self, *, now: datetime | None = None) -> None:
        self.enabled = True
        self.updated_at = now or datetime.now(UTC)

    def update(
        self,
        *,
        system_prompt: str,
        capabilities: tuple[str, ...],
        now: datetime | None = None,
    ) -> None:
        if not system_prompt.strip():
            raise ValueError("system prompt is required")
        self.system_prompt = system_prompt.strip()
        self.capabilities = tuple(
            sorted({value.strip().lower() for value in capabilities if value.strip()})
        )
        self.version += 1
        self.updated_at = now or datetime.now(UTC)

