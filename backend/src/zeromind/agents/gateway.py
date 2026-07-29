import uuid
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from zeromind.agents.pi_rpc import PiClient, PiRpcRequest
from zeromind.agents.registry import AgentRegistry


class AgentInputError(ValueError):
    pass


class AgentOutputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    agent_id: uuid.UUID
    agent_version: int
    provider: str
    model: str
    output: dict[str, object]
    usage: dict[str, int | float]


class AgentGateway:
    def __init__(self, registry: AgentRegistry, client: PiClient) -> None:
        self._registry = registry
        self._client = client

    async def execute(
        self,
        agent_id: uuid.UUID,
        input: dict[str, object],
        *,
        timeout_seconds: float = 120,
    ) -> AgentExecutionResult:
        definition = await self._registry.get_agent(agent_id)
        if not definition.enabled:
            raise ValueError("agent is disabled")
        profile = await self._registry.get_provider(definition.provider_profile_id)
        if not profile.enabled:
            raise ValueError("provider profile is disabled")
        try:
            Draft202012Validator(definition.input_schema).validate(input)
        except ValidationError as error:
            raise AgentInputError(error.message) from error

        result = await self._client.execute(
            PiRpcRequest(
                provider=profile.provider,
                model=profile.model,
                api_key=profile.resolve_api_key(),
                thinking_level=profile.thinking_level,
                system_prompt=definition.system_prompt,
                input=input,
                output_schema=definition.output_schema,
            ),
            timeout_seconds=timeout_seconds,
        )
        try:
            Draft202012Validator(definition.output_schema).validate(result.output)
        except ValidationError as error:
            raise AgentOutputError(error.message) from error
        return AgentExecutionResult(
            agent_id=definition.id,
            agent_version=definition.version,
            provider=profile.provider,
            model=profile.model,
            output=result.output,
            usage=result.usage,
        )
