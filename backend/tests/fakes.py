"""Real Anthropic SDK clients talking to an in-memory HTTP transport."""

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2


class Recorder:
    def __init__(self, respond: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.requests: list[httpx2.Request] = []
        self._respond = respond

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._respond(request)

    @property
    def body(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)


def anthropic_client(recorder: Recorder) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(recorder.handler)
        ),
    )


def claude_message(
    data: Any, *, model: str = "claude-opus-5-5", stop_reason: str = "end_turn"
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    if data is not None:
        text = data if isinstance(data, str) else json.dumps(data)
        content.append({"type": "text", "text": text})
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 200},
    }


def ok(payload: dict[str, Any]) -> Callable[[httpx2.Request], httpx2.Response]:
    return lambda _: httpx2.Response(200, json=payload)


def api_error(status: int, error_type: str) -> Callable[[httpx2.Request], httpx2.Response]:
    return lambda _: httpx2.Response(
        status, json={"type": "error", "error": {"type": error_type, "message": "x"}}
    )
