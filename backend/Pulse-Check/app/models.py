"""Pydantic models for API payloads."""

from pydantic import BaseModel, Field


class MonitorCreate(BaseModel):
    """Body for POST /monitors."""

    id: str = Field(..., min_length=1, max_length=256, description="Unique monitor / device id.")
    timeout: int = Field(..., ge=1, le=86_400, description="Countdown duration in seconds.")
    alert_email: str = Field(..., min_length=3, max_length=320, description="Email for alerts (stored).")


class MonitorRegisterResponse(BaseModel):
    """Response after creating a monitor."""

    message: str
