"""Pydantic models for API payloads."""

from typing import Literal

from pydantic import BaseModel, Field

MonitorStatus = Literal["up", "down", "paused"]


class MonitorCreate(BaseModel):
    """Body for POST /monitors."""

    id: str = Field(..., min_length=1, max_length=256, description="Unique monitor / device id.")
    timeout: int = Field(..., ge=1, le=86_400, description="Countdown duration in seconds.")
    alert_email: str = Field(..., min_length=3, max_length=320, description="Email for alerts (stored).")


class MonitorRegisterResponse(BaseModel):
    """Response after creating a monitor."""

    message: str


class MonitorDetail(BaseModel):
    """Observability payload for a single monitor."""

    id: str
    status: MonitorStatus
    timeout: int
    alert_email: str
    seconds_remaining: float | None = Field(
        default=None,
        description="Seconds until timeout when status is up and a deadline is set.",
    )
