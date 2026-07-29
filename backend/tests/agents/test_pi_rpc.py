import sys

import pytest

from zeromind.agents.pi_rpc import (
    PiProtocolError,
    PiRpcClient,
    PiRpcRequest,
)

RUNNER = r"""
import json
import sys

request = json.loads(sys.stdin.readline())
print(json.dumps({"id": request["id"], "type": "delta", "delta": "working"}), flush=True)
print(json.dumps({
    "id": request["id"],
    "type": "completed",
    "output": {"summary": request["input"]["title"]},
    "usage": {"input": 10, "output": 4, "cost": 0.01}
}), flush=True)
"""

MALFORMED_RUNNER = r"""
import sys
_ = sys.stdin.readline()
print("not-json", flush=True)
"""


def request() -> PiRpcRequest:
    return PiRpcRequest(
        provider="openai",
        model="gpt-5-mini",
        api_key="secret",
        thinking_level="medium",
        system_prompt="Analyze.",
        input={"title": "Article"},
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
    )


@pytest.mark.asyncio
async def test_rpc_client_correlates_events_and_returns_structured_result() -> None:
    client = PiRpcClient(command=(sys.executable, "-u", "-c", RUNNER))

    result = await client.execute(request(), timeout_seconds=2)

    assert result.output == {"summary": "Article"}
    assert result.deltas == ("working",)
    assert result.usage["input"] == 10


@pytest.mark.asyncio
async def test_rpc_client_rejects_malformed_jsonl() -> None:
    client = PiRpcClient(command=(sys.executable, "-u", "-c", MALFORMED_RUNNER))

    with pytest.raises(PiProtocolError, match="invalid JSON"):
        await client.execute(request(), timeout_seconds=2)

