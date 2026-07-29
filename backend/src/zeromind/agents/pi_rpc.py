import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol


class PiProtocolError(RuntimeError):
    pass


class PiExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PiRpcRequest:
    provider: str
    model: str
    api_key: str
    thinking_level: str
    system_prompt: str
    input: dict[str, object]
    output_schema: dict[str, object]


@dataclass(frozen=True, slots=True)
class PiRpcResult:
    output: dict[str, object]
    deltas: tuple[str, ...]
    usage: dict[str, int | float]


class PiClient(Protocol):
    async def execute(
        self,
        request: PiRpcRequest,
        *,
        timeout_seconds: float,
    ) -> PiRpcResult: ...


class PiRpcClient:
    def __init__(self, *, command: tuple[str, ...]) -> None:
        if not command:
            raise ValueError("Pi runner command is required")
        self._command = command

    async def execute(
        self,
        request: PiRpcRequest,
        *,
        timeout_seconds: float,
    ) -> PiRpcResult:
        process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdin is None or process.stdout is None:
            process.kill()
            raise PiProtocolError("Pi runner pipes are unavailable")
        request_id = str(uuid.uuid4())
        payload = {"id": request_id, "type": "execute", **asdict(request)}
        process.stdin.write(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            + b"\n"
        )
        await process.stdin.drain()
        process.stdin.close()

        deltas: list[str] = []
        try:
            async with asyncio.timeout(timeout_seconds):
                while line := await process.stdout.readline():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise PiProtocolError("Pi runner emitted invalid JSON") from error
                    if not isinstance(event, dict) or event.get("id") != request_id:
                        raise PiProtocolError("Pi runner emitted an uncorrelated event")
                    event_type = event.get("type")
                    if event_type == "delta":
                        deltas.append(str(event.get("delta", "")))
                    elif event_type == "failed":
                        raise PiExecutionError(str(event.get("message", "Pi execution failed")))
                    elif event_type == "completed":
                        output = event.get("output")
                        usage = event.get("usage", {})
                        if not isinstance(output, dict) or not isinstance(usage, dict):
                            raise PiProtocolError("Pi completion payload is invalid")
                        await process.wait()
                        return PiRpcResult(
                            output=output,
                            deltas=tuple(deltas),
                            usage={
                                str(key): value
                                for key, value in usage.items()
                                if isinstance(value, int | float)
                            },
                        )
                stderr = (
                    (await process.stderr.read()).decode(errors="replace")
                    if process.stderr
                    else ""
                )
                raise PiProtocolError(
                    f"Pi runner exited before completion: {stderr.strip()}"
                )
        except TimeoutError as error:
            raise PiExecutionError("Pi execution timed out") from error
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

