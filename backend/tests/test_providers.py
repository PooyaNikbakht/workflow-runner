import pytest

from app.models import PainPoints, TicketClassification
from app.providers import build_provider
from app.providers.anthropic import FALLBACK_BETA, AnthropicProvider
from app.providers.base import ProviderError, Task
from app.providers.mock import MockProvider
from app.settings import Settings
from app.workflows import companies
from tests.fakes import Recorder, anthropic_client, api_error, claude_message, ok

COMPANY = companies()["harborline-freight.example"].model_dump()
TASK = Task(
    name="pain point extraction",
    system="You help qualify leads.",
    instructions="List the pain points.",
    output=PainPoints,
    context={"lead": {"name": "Marta"}, "company": COMPANY},
)
VALID = {
    "summary": "Quotes are slow.",
    "pain_points": [{"title": "Slow quotes", "evidence": "26 hours", "impact": "high"}],
}


async def test_structured_output_request_and_validated_result():
    rec = Recorder(ok(claude_message(VALID)))
    provider = AnthropicProvider(anthropic_client(rec), model="claude-opus-5-5", effort="medium")

    result = await provider.generate(TASK)

    assert isinstance(result, PainPoints)
    assert result.pain_points[0].impact == "high"
    body = rec.body
    assert body["model"] == "claude-opus-5-5"
    assert body["system"] == "You help qualify leads."
    assert body["output_config"]["effort"] == "medium"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert "pain_points" in fmt["schema"]["properties"]
    for key in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):
        assert key not in body
    [message] = body["messages"]
    assert message["role"] == "user"
    assert "Harborline Freight" in message["content"]
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in rec.requests[-1].headers["anthropic-beta"]


async def test_haiku_has_no_server_side_fallback():
    rec = Recorder(ok(claude_message(VALID, model="claude-haiku-5-5")))
    provider = AnthropicProvider(anthropic_client(rec), model="claude-haiku-5-5")
    await provider.generate(TASK)
    assert "fallbacks" not in rec.body
    assert "anthropic-beta" not in rec.requests[-1].headers


@pytest.mark.parametrize(
    ("status", "error_type", "code", "retryable"),
    [
        (429, "rate_limit_error", "provider_busy", True),
        (500, "api_error", "provider_error", True),
        (529, "overloaded_error", "provider_error", True),
        (401, "authentication_error", "provider_auth", False),
        (400, "invalid_request_error", "provider_rejected", False),
    ],
)
async def test_api_errors_map_to_retryable_flags(status, error_type, code, retryable):
    provider = AnthropicProvider(
        anthropic_client(Recorder(api_error(status, error_type))), model="claude-opus-5-5"
    )
    with pytest.raises(ProviderError) as info:
        await provider.generate(TASK)
    assert info.value.code == code
    assert info.value.retryable is retryable


async def test_refusal_is_not_retried():
    rec = Recorder(ok(claude_message(None, stop_reason="refusal")))
    provider = AnthropicProvider(anthropic_client(rec), model="claude-opus-5-5")
    with pytest.raises(ProviderError) as info:
        await provider.generate(TASK)
    assert info.value.code == "refused" and info.value.retryable is False


async def test_output_that_breaks_the_schema_is_retryable():
    bad = {"summary": "x", "pain_points": [{"title": "t", "evidence": "e", "impact": "huge"}]}
    rec = Recorder(ok(claude_message(bad)))
    provider = AnthropicProvider(anthropic_client(rec), model="claude-opus-5-5")
    with pytest.raises(ProviderError) as info:
        await provider.generate(TASK)
    assert info.value.code == "invalid_output" and info.value.retryable is True


async def test_mock_is_deterministic_and_schema_valid():
    first = await MockProvider().generate(TASK)
    second = await MockProvider().generate(TASK)
    assert first == second
    assert first.pain_points[0].title == "Manual email handling"


async def test_mock_refuses_unknown_tasks():
    task = Task(name="x", system="", instructions="", output=Settings)  # type: ignore[arg-type]
    with pytest.raises(ProviderError):
        await MockProvider().generate(task)


async def test_mock_classifies_tickets():
    ticket = {
        "customer_name": "Tom",
        "plan": "team",
        "subject": "Bank sync not updating",
        "message": "Sync failed with an error, we need it before month end.",
    }
    task = Task(
        name="c",
        system="",
        instructions="",
        output=TicketClassification,
        context={"ticket": ticket},
    )
    result = await MockProvider().generate(task)
    assert (result.category, result.priority) == ("bug", "high")


def test_factory_picks_provider_from_settings():
    offline = build_provider(Settings(_env_file=None, anthropic_api_key=""))
    assert offline.name == "offline"
    live = build_provider(Settings(_env_file=None, anthropic_api_key="sk-test"))
    assert isinstance(live, AnthropicProvider) and live.model == "claude-opus-5-5"
    forced = build_provider(
        Settings(_env_file=None, anthropic_api_key="sk-test", llm_provider="offline")
    )
    assert forced.name == "offline"
    haiku = build_provider(
        Settings(_env_file=None, anthropic_api_key="sk-test", anthropic_model="claude-haiku-5-5")
    )
    assert haiku.model == "claude-haiku-5-5"
