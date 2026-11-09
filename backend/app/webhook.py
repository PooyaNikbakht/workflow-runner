"""Outgoing webhooks: signed with HMAC-SHA256 and sent with an idempotency key."""

import hashlib
import hmac
from typing import Any

import httpx

from app.db import dumps, now
from app.errors import PermanentError, TransientError

SIGNATURE_HEADER = "X-Runner-Signature"
IDEMPOTENCY_HEADER = "Idempotency-Key"


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(sign(secret, body), signature or "")


class WebhookSender:
    def __init__(
        self,
        url: str,
        secret: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url
        self.secret = secret
        self.timeout = timeout
        self.transport = transport

    async def send(self, event: str, data: dict[str, Any], *, key: str) -> dict[str, Any]:
        """POST the event. The same key on a re-run lets the receiver drop the duplicate."""
        body = dumps({"id": key, "event": event, "created_at": now(), "data": data}).encode()
        headers = {
            "Content-Type": "application/json",
            IDEMPOTENCY_HEADER: key,
            SIGNATURE_HEADER: sign(self.secret, body),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(self.url, content=body, headers=headers)
        except httpx.TransportError as exc:
            raise TransientError(
                f"Couldn't reach the webhook endpoint ({type(exc).__name__})."
            ) from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise TransientError(f"Webhook endpoint answered {response.status_code}.")
        if response.status_code >= 400:
            raise PermanentError(
                f"Webhook endpoint rejected the delivery ({response.status_code})."
            )
        try:
            reply = response.json()
        except ValueError:
            reply = {}
        return {"status_code": response.status_code, "receiver": reply, "url": self.url}
