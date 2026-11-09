"""Claude adapter: structured outputs through `messages.parse`, validated by pydantic.

The output schema comes from the step's pydantic model, so the API constrains the answer to that
JSON schema and the SDK hands back a validated instance. Errors map to `ProviderError` with a
`retryable` flag, and the engine decides whether to retry with backoff.
"""

import json
import logging
from typing import Any

import anthropic
import pydantic
from pydantic import BaseModel

from app.providers.base import ProviderError, Task

logger = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
# Claude Haiku 5.5 has no server-side fallback, so it is not listed.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def supports_refusal_fallback(model: str) -> bool:
    return model in FALLBACK_MODELS


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        *,
        model: str,
        effort: str = "medium",
        max_tokens: int = 16000,
    ) -> None:
        self.client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def build_params(self, task: Task[Any]) -> dict[str, Any]:
        # No temperature, top_p, thinking config, tool_choice or prefill: thinking is always on
        # for this model family and effort is the control.
        data = json.dumps(task.context, indent=2, ensure_ascii=False)
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": task.system,
            "messages": [
                {
                    "role": "user",
                    "content": f"<input>\n{data}\n</input>\n\n{task.instructions}",
                }
            ],
            "output_config": {"effort": self.effort},
        }

    async def generate[T: BaseModel](self, task: Task[T]) -> T:
        params = self.build_params(task)
        try:
            if supports_refusal_fallback(self.model):
                response = await self.client.beta.messages.parse(
                    **params,
                    output_format=task.output,
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                )
            else:
                response = await self.client.messages.parse(**params, output_format=task.output)
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise ProviderError(
                "provider_unavailable", "Couldn't reach Claude.", retryable=True
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError(
                "provider_busy", "Claude is busy right now.", retryable=True
            ) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderError(
                "provider_auth", "The Claude API key was rejected.", retryable=False
            ) from exc
        except anthropic.BadRequestError as exc:
            logger.warning("Claude rejected the request: %s", exc.message)
            raise ProviderError(
                "provider_rejected", "Claude rejected the request.", retryable=False
            ) from exc
        except anthropic.APIStatusError as exc:
            logger.warning("Claude API error %s: %s", exc.status_code, exc.message)
            raise ProviderError(
                "provider_error",
                f"Claude returned an error ({exc.status_code}).",
                retryable=exc.status_code >= 500,
            ) from exc
        except pydantic.ValidationError as exc:
            raise ProviderError(
                "invalid_output", "Claude's answer didn't match the schema.", retryable=True
            ) from exc

        if response.stop_reason == "refusal":
            raise ProviderError("refused", "Claude declined this request.", retryable=False)
        if response.stop_reason == "max_tokens":
            raise ProviderError("too_long", "Claude ran out of output tokens.", retryable=False)
        if response.parsed_output is None:
            raise ProviderError("empty_output", "Claude returned no data.", retryable=True)
        return response.parsed_output
