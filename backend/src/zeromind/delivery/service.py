import asyncio
import hashlib
import hmac
import json
import os
from collections.abc import Awaitable, Callable

import httpx

from zeromind.content.network_policy import NetworkPolicy
from zeromind.delivery.domain import DeliveryResult, WebhookEndpoint

Sleep = Callable[[float], Awaitable[None]]


class WebhookDeliveryService:
    def __init__(
        self,
        *,
        network_policy: NetworkPolicy,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 15,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._policy = network_policy
        self._transport = transport
        self._timeout = timeout_seconds
        self._sleep = sleep

    async def deliver(
        self,
        endpoint: WebhookEndpoint,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> DeliveryResult:
        if not endpoint.enabled or event_type not in endpoint.events:
            return DeliveryResult(
                endpoint_id=endpoint.id,
                event_id=event_id,
                status="skipped",
                attempts=0,
                response_status=None,
                error=None,
            )
        await self._policy.validate_url(endpoint.url)
        secret = os.environ.get(endpoint.secret_env)
        if not secret:
            raise ValueError(
                f"webhook secret environment variable {endpoint.secret_env} is missing"
            )
        body = json.dumps(
            {"id": event_id, "type": event_type, "data": payload},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        last_status: int | None = None
        last_error: str | None = None
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            follow_redirects=False,
        ) as client:
            for attempt in range(1, endpoint.max_attempts + 1):
                try:
                    response = await client.post(
                        endpoint.url,
                        content=body,
                        headers={
                            "content-type": "application/json",
                            "x-zeromind-event": event_type,
                            "x-zeromind-delivery": event_id,
                            "x-zeromind-signature": f"sha256={signature}",
                        },
                    )
                    last_status = response.status_code
                    if 200 <= response.status_code < 300:
                        return DeliveryResult(
                            endpoint_id=endpoint.id,
                            event_id=event_id,
                            status="delivered",
                            attempts=attempt,
                            response_status=response.status_code,
                            error=None,
                        )
                    last_error = f"HTTP {response.status_code}"
                except httpx.HTTPError as error:
                    last_error = str(error)
                if attempt < endpoint.max_attempts:
                    await self._sleep(float(2 ** (attempt - 1)))
        return DeliveryResult(
            endpoint_id=endpoint.id,
            event_id=event_id,
            status="exhausted",
            attempts=endpoint.max_attempts,
            response_status=last_status,
            error=last_error,
        )
