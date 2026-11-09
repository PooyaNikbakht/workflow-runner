"""Provider adapters behind one interface, plus the factory that picks one from settings."""

from app.providers.base import LLM, ProviderError, Task
from app.settings import Settings


def build_provider(settings: Settings) -> LLM:
    """Create the active adapter. The Anthropic SDK is imported only when it is used."""
    if settings.provider == "anthropic":
        import anthropic

        from app.providers.anthropic import AnthropicProvider

        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None,
            timeout=settings.provider_timeout_seconds,
            # The engine owns retries (with backoff and a visible log), so the SDK makes one try.
            max_retries=0,
        )
        return AnthropicProvider(
            client,
            model=settings.anthropic_model,
            effort=settings.anthropic_effort,
            max_tokens=settings.anthropic_max_tokens,
        )

    from app.providers.mock import MockProvider

    return MockProvider(delay_seconds=settings.step_delay_seconds)


__all__ = ["LLM", "ProviderError", "Task", "build_provider"]
