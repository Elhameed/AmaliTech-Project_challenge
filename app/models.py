"""Pydantic models for request/response payloads."""

from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    """JSON body for /process-payment."""

    amount: int = Field(..., ge=1, description="Charge amount as a positive integer.")
    currency: str = Field(..., min_length=1, max_length=16, description="ISO-like currency code.")


class PaymentResponse(BaseModel):
    """Successful charge response."""

    message: str = Field(..., description='Human-readable status, e.g. "Charged 100 GHS".')

