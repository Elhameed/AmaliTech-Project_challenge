"""In-memory monitor store (registration only until scheduler is added)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from collections.abc import Callable
from typing import Literal

from app.models import MonitorCreate

MonitorStatus = Literal["up", "down", "paused"]


@dataclass
class Monitor:
    """Runtime state for one device monitor."""

    id: str
    timeout_seconds: int
    alert_email: str
    status: MonitorStatus = "up"
    deadline: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DuplicateMonitorError(Exception):
    """Raised when registering a monitor id that already exists."""


class MonitorStore:
    """Thread-safe (asyncio) in-memory monitor registry."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._monitors: dict[str, Monitor] = {}

    async def register(self, payload: MonitorCreate) -> Monitor:
        async with self._lock:
            if payload.id in self._monitors:
                raise DuplicateMonitorError
            now = datetime.now(UTC)
            mon = Monitor(
                id=payload.id,
                timeout_seconds=payload.timeout,
                alert_email=payload.alert_email,
                status="up",
                deadline=now + timedelta(seconds=payload.timeout),
                created_at=now,
                updated_at=now,
            )
            self._monitors[payload.id] = mon
            return mon

    async def heartbeat(self, monitor_id: str) -> Monitor:
        """Reset countdown; unpause if paused; revive if down (documented behavior)."""
        async with self._lock:
            mon = self._monitors.get(monitor_id)
            if mon is None:
                raise KeyError(monitor_id)
            now = datetime.now(UTC)
            if mon.status == "paused":
                mon.status = "up"
            elif mon.status == "down":
                mon.status = "up"
            mon.deadline = now + timedelta(seconds=mon.timeout_seconds)
            mon.updated_at = now
            return mon

    async def pause(self, monitor_id: str) -> Monitor:
        """Stop countdown; no alerts while paused."""
        async with self._lock:
            mon = self._monitors.get(monitor_id)
            if mon is None:
                raise KeyError(monitor_id)
            now = datetime.now(UTC)
            mon.status = "paused"
            mon.deadline = None
            mon.updated_at = now
            return mon

    async def process_expired_monitors(
        self,
        *,
        emit_alert: Callable[[str], None],
        now: datetime | None = None,
    ) -> None:
        """Mark monitors as down when deadline passes; invoke emit_alert once per monitor."""
        current = now or datetime.now(UTC)
        async with self._lock:
            for mon in list(self._monitors.values()):
                if mon.status != "up" or mon.deadline is None:
                    continue
                if current < mon.deadline:
                    continue
                mon_id = mon.id
                mon.status = "down"
                mon.deadline = None
                mon.updated_at = current
                emit_alert(mon_id)
