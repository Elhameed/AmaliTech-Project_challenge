"""FastAPI entrypoint."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi import Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.models import PaymentRequest, PaymentResponse

app = FastAPI(
    title="Idempotency-Gateway",
    description='Pay-once protocol: POST /process-payment with "Idempotency-Key" header.',
    version="0.1.0",
)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""
    return {"status": "ok"}


@app.post(
    "/process-payment",
    tags=["payments"],
    summary="Process a payment (no replay yet)",
)
async def process_payment(
    payment: PaymentRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """
    Simulate payment processing (~2 seconds) and return a success response.

    This endpoint requires the Idempotency-Key header, but does not yet implement
    replay semantics (added in the next commits).
    """
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing required header "Idempotency-Key".',
        )

    await asyncio.sleep(2)
    payload = PaymentResponse(message=f"Charged {payment.amount} {payment.currency}").model_dump()
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)

