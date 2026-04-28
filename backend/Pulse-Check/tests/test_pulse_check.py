"""Pulse-Check API behavior."""

import asyncio
import json
import logging

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_monitor_201(client: AsyncClient) -> None:
    response = await client.post(
        "/monitors",
        json={"id": "device-a", "timeout": 60, "alert_email": "a@example.com"},
    )
    assert response.status_code == 201
    assert "registered" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_returns_409(client: AsyncClient) -> None:
    body = {"id": "device-dup", "timeout": 10, "alert_email": "x@example.com"}
    assert (await client.post("/monitors", json=body)).status_code == 201
    second = await client.post("/monitors", json=body)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_heartbeat_unknown_returns_404(client: AsyncClient) -> None:
    response = await client.post("/monitors/missing/heartbeat")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_monitor_returns_detail(client: AsyncClient) -> None:
    await client.post(
        "/monitors",
        json={"id": "device-b", "timeout": 10, "alert_email": "b@example.com"},
    )
    detail = await client.get("/monitors/device-b")
    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == "device-b"
    assert data["status"] == "up"
    assert data["timeout"] == 10
    assert data["seconds_remaining"] is not None


@pytest.mark.asyncio
async def test_timeout_fires_alert_and_marks_down(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="pulse_check.alert")
    await client.post(
        "/monitors",
        json={"id": "device-down", "timeout": 1, "alert_email": "c@example.com"},
    )
    await asyncio.sleep(1.15)
    state = await client.get("/monitors/device-down")
    assert state.json()["status"] == "down"

    alert_lines = [r.getMessage() for r in caplog.records if r.name == "pulse_check.alert"]
    parsed = [json.loads(line) for line in alert_lines]
    assert any(p.get("ALERT") == "Device device-down is down!" for p in parsed)


@pytest.mark.asyncio
async def test_pause_prevents_timeout_alert(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="pulse_check.alert")
    await client.post(
        "/monitors",
        json={"id": "device-paused", "timeout": 1, "alert_email": "d@example.com"},
    )
    assert (await client.post("/monitors/device-paused/pause")).status_code == 200
    await asyncio.sleep(1.15)

    state = await client.get("/monitors/device-paused")
    assert state.json()["status"] == "paused"

    alert_lines = [r.getMessage() for r in caplog.records if r.name == "pulse_check.alert"]
    assert not any("device-paused" in line for line in alert_lines)

    assert (await client.post("/monitors/device-paused/heartbeat")).status_code == 200
    revived = await client.get("/monitors/device-paused")
    assert revived.json()["status"] == "up"
