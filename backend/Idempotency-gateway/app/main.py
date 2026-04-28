"""FastAPI entrypoint."""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI
from fastapi import Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.idempotency_store import IdempotencyStore, StoredResponse, fingerprint_payment
from app.models import PaymentRequest, PaymentResponse

app = FastAPI(
    title="Idempotency-Gateway",
    description='Pay-once protocol: POST /process-payment with "Idempotency-Key" header.',
    version="0.1.0",
)


@app.on_event("startup")
async def _startup() -> None:
    app.state.idempotency_store = IdempotencyStore()


def _get_store() -> IdempotencyStore:
    return app.state.idempotency_store


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""
    return {"status": "ok"}


@app.post(
    "/process-payment",
    tags=["payments"],
    summary="Process a payment (replay enabled)",
)
async def process_payment(
    payment: PaymentRequest,
    store: IdempotencyStore = Depends(_get_store),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """
    Simulate payment processing (~2 seconds) and return a success response.

    This endpoint requires the Idempotency-Key header and guarantees at-most-once
    processing per key/body. Concurrent identical requests wait for the first.
    """
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing required header "Idempotency-Key".',
        )

    key = idempotency_key.strip()
    request_hash = fingerprint_payment(payment)

    try:
        kind, rec = await store.decide(key, request_hash)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key already used for a different request body.",
        ) from None

    if kind == "replay":
        assert rec.response is not None
        return JSONResponse(
            status_code=rec.response.status_code,
            content=rec.response.body,
            headers={"X-Cache-Hit": "true"},
        )

    if kind == "waiter":
        await rec.done.wait()
        assert rec.response is not None
        return JSONResponse(
            status_code=rec.response.status_code,
            content=rec.response.body,
            headers={"X-Cache-Hit": "true"},
        )

    await asyncio.sleep(2)
    payload = PaymentResponse(message=f"Charged {payment.amount} {payment.currency}").model_dump()
    await store.complete(
        key,
        StoredResponse(request_hash=request_hash, status_code=status.HTTP_201_CREATED, body=payload),
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)

