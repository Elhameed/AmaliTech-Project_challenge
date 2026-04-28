"""Pytest fixtures."""

from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Speed up suite runs; avoid cleanup loop during tests."""
    monkeypatch.setenv("PAYMENT_DELAY_SECONDS", "0.05")
    monkeypatch.setenv("CLEANUP_INTERVAL_SECONDS", "3600")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client with ASGI lifespan (store initialized)."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

