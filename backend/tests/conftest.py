from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.engine import Engine
from app.main import create_app
from app.providers.mock import MockProvider
from app.queue import SqliteQueue
from app.settings import Settings
from app.webhook import WebhookSender
from app.workflows import samples

RECEIVER = "http://testserver/api/receiver/hooks"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        llm_provider="offline",
        anthropic_api_key="",
        step_delay_seconds=0,
        retry_base_seconds=0,
        sse_poll_seconds=0.01,
        webhook_url=RECEIVER,
        webhook_secret="test-secret",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(settings):
    database = Database(settings.db_path)
    yield database
    database.close()


@pytest.fixture
def queue(db):
    return SqliteQueue(db, lease_seconds=30)


def make_engine(db, queue, app, settings, transport: httpx.AsyncBaseTransport | None = None):
    """A worker-side engine whose webhook posts straight into the API's mock receiver."""
    return Engine(
        db,
        queue,
        provider=MockProvider(),
        webhook=WebhookSender(
            settings.webhook_url,
            settings.webhook_secret,
            transport=transport or httpx.ASGITransport(app=app),
        ),
        retry_base=settings.retry_base_seconds,
        retry_max=settings.retry_max_seconds,
    )


@pytest.fixture
def engine(db, queue, app, settings):
    return make_engine(db, queue, app, settings)


def sample(workflow: str, index: int = 0) -> dict:
    return dict(samples()[workflow][index]["input"])
