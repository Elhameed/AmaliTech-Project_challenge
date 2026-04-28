"""Idempotency behavior: happy path, replay, mismatch, and in-flight."""

import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_process_payment_happy_path_returns_201_and_message(client: AsyncClient) -> None:
    response = await client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "key-happy-1"},
    )
    assert response.status_code == 201
    assert response.json() == {"message": "Charged 100 GHS"}
    assert response.headers.get("X-Cache-Hit") is None


@pytest.mark.asyncio
async def test_replay_same_key_and_body_cache_hit_header(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "key-replay-1"}
    body = {"amount": 50, "currency": "USD"}

    first = await client.post("/process-payment", json=body, headers=headers)
    assert first.status_code == 201

    second = await client.post("/process-payment", json=body, headers=headers)
    assert second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("X-Cache-Hit") == "true"


@pytest.mark.asyncio
async def test_canonical_body_same_hash_different_key_order(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "key-canonical-1"}
    await client.post(
        "/process-payment",
        content='{"currency":"EUR","amount":10}',
        headers={**headers, "Content-Type": "application/json"},
    )
    replay = await client.post(
        "/process-payment",
        content='{"amount":10,"currency":"EUR"}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert replay.status_code == 201
    assert replay.headers.get("X-Cache-Hit") == "true"
    assert replay.json() == {"message": "Charged 10 EUR"}


@pytest.mark.asyncio
async def test_mismatch_same_key_different_body_returns_409(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "key-mismatch-1"}
    first = await client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers=headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/process-payment",
        json={"amount": 500, "currency": "GHS"},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json() == {"detail": "Idempotency key already used for a different request body."}


@pytest.mark.asyncio
async def test_missing_idempotency_key_returns_400(client: AsyncClient) -> None:
    response = await client.post("/process-payment", json={"amount": 1, "currency": "GHS"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_identical_requests_wait_and_replay(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "key-concurrent-1"}
    body = {"amount": 7, "currency": "GHS"}

    async def pay() -> object:
        return await client.post("/process-payment", json=body, headers=headers)

    results = await asyncio.gather(pay(), pay())
    assert {r.status_code for r in results} == {201}
    assert {tuple(sorted(r.json().items())) for r in results} == {(("message", "Charged 7 GHS"),)}
    assert set(r.headers.get("X-Cache-Hit") for r in results) == {None, "true"}


@pytest.mark.asyncio
async def test_mismatch_while_in_flight_returns_409(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "key-inflight-mismatch"}
    body_a = {"amount": 1, "currency": "GHS"}
    body_b = {"amount": 2, "currency": "GHS"}

    task = asyncio.create_task(client.post("/process-payment", json=body_a, headers=headers))
    await asyncio.sleep(0.01)
    conflict = await client.post("/process-payment", json=body_b, headers=headers)
    first = await task

    assert first.status_code == 201
    assert conflict.status_code == 409

