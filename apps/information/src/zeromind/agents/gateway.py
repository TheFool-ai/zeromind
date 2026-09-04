import hashlib
import json
import uuid
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from zeromind.agents.pi_rpc import PiClient, PiExecutionError, PiRpcRequest
from zeromind.agents.registry import AgentRegistry
from zeromind.agents.sanitization import bounded_error, sanitize_agent_input
from zeromind.agents.session_domain import AgentExecutionContext, AgentSession
from zeromind.agents.session_repository import AgentSessionRepository
from zeromind.agents.validators import AgentOutputError, validate_agent_semantics


class AgentInputError(ValueError):
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
    def __init__(
        self,
        registry: AgentRegistry,
        client: PiClient,
        sessions: AgentSessionRepository | None = None,
    ) -> None:
        self._registry = registry
        self._client = client
        self._sessions = sessions

    async def execute(
        self,
        agent_id: uuid.UUID,
        input: dict[str, object],
        *,
        context: AgentExecutionContext | None = None,
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

        trace: AgentSession | None = None
        if context is not None and self._sessions is not None:
            sanitized = sanitize_agent_input(input)
            trace = AgentSession.start(
                context=context,
                agent_id=definition.id,
                agent_version_id=definition.version_id,
                provider=profile.provider,
                model=profile.model,
                thinking_level=profile.thinking_level,
                sanitized_input=sanitized.value,
                document_sha256=sanitized.document_sha256,
                document_character_count=sanitized.document_character_count,
            )
            await self._sessions.add(trace)
        try:
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
        except PiExecutionError as error:
            if trace is not None:
                status = error.code if error.code in {
                    "provider_failed",
                    "timed_out",
                    "protocol_failed",
                    "json_invalid",
                    "cancelled",
                } else "protocol_failed"
                trace.fail(
                    status=status,  # type: ignore[arg-type]
                    error_code=error.code,
                    error_message=bounded_error(str(error)),
                    response_sha256=error.response_sha256,
                    response_character_count=error.response_character_count,
                )
                await self._sessions.save(trace)  # type: ignore[union-attr]
            raise
        except Exception as error:
            if trace is not None:
                trace.fail(
                    status="provider_failed",
                    error_code="provider_configuration_error",
                    error_message=bounded_error(str(error)),
                )
                await self._sessions.save(trace)  # type: ignore[union-attr]
            raise
        try:
            Draft202012Validator(definition.output_schema).validate(result.output)
            validate_agent_semantics(definition.capabilities, result.output)
        except ValidationError as error:
            await self._fail_schema(trace, error.message, result)
            raise AgentOutputError(error.message) from error
        except AgentOutputError as error:
            await self._fail_schema(trace, str(error), result)
            raise
        if trace is not None:
            response_sha256, response_character_count = self._response_diagnostics(
                result.output,
                result.response_sha256,
                result.response_character_count,
            )
            trace.complete(
                output=result.output,
                usage=result.usage,
                response_sha256=response_sha256,
                response_character_count=response_character_count,
            )
            await self._sessions.save(trace)  # type: ignore[union-attr]
        return AgentExecutionResult(
            agent_id=definition.id,
            agent_version=definition.version,
            provider=profile.provider,
            model=profile.model,
            output=result.output,
            usage=result.usage,
        )

    async def _fail_schema(
        self,
        trace: AgentSession | None,
        message: str,
        result: object,
    ) -> None:
        if trace is None:
            return
        response_sha256, response_character_count = self._response_diagnostics(
            result.output,  # type: ignore[attr-defined]
            result.response_sha256,  # type: ignore[attr-defined]
            result.response_character_count,  # type: ignore[attr-defined]
        )
        trace.fail(
            status="schema_invalid",
            error_code="agent_output_schema_invalid",
            error_message=bounded_error(message),
            response_sha256=response_sha256,
            response_character_count=response_character_count,
        )
        await self._sessions.save(trace)  # type: ignore[union-attr]

    @staticmethod
    def _response_diagnostics(
        output: dict[str, object],
        response_sha256: str | None,
        response_character_count: int | None,
    ) -> tuple[str, int]:
        serialized = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return (
            response_sha256 or hashlib.sha256(serialized.encode()).hexdigest(),
            response_character_count if response_character_count is not None else len(serialized),
        )
