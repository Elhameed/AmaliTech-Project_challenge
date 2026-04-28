"""FastAPI entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from app.config import Settings, load_settings
from app.models import MonitorCreate, MonitorDetail, MonitorRegisterResponse, MonitorStatus
from app.scheduler import scheduler_loop
from app.store import DuplicateMonitorError, Monitor, MonitorStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    store = MonitorStore()
    scheduler_task = asyncio.create_task(scheduler_loop(store, settings))
    app.state.settings = settings
    app.state.store = store
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Pulse-Check-API",
    description="Dead man's switch: monitors with countdown timers and heartbeats.",
    version="0.1.0",
    lifespan=lifespan,
)


def get_store(request: Request) -> MonitorStore:
    return request.app.state.store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _monitor_to_detail(mon: Monitor) -> MonitorDetail:
    now = datetime.now(UTC)
    remaining: float | None = None
    if mon.status == "up" and mon.deadline is not None:
        remaining = max(0.0, (mon.deadline - now).total_seconds())
    return MonitorDetail(
        id=mon.id,
        status=mon.status,
        timeout=mon.timeout_seconds,
        alert_email=mon.alert_email,
        seconds_remaining=remaining,
    )


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post(
    "/monitors",
    status_code=status.HTTP_201_CREATED,
    tags=["monitors"],
    summary="Register a new monitor",
)
async def create_monitor(
    payload: MonitorCreate,
    store: MonitorStore = Depends(get_store),
) -> MonitorRegisterResponse:
    """Create a monitor and start its countdown timer."""
    try:
        await store.register(payload)
    except DuplicateMonitorError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Monitor id "{payload.id}" already exists.',
        ) from None
    return MonitorRegisterResponse(message=f'Monitor "{payload.id}" registered and timer started.')


@app.post(
    "/monitors/{monitor_id}/heartbeat",
    status_code=status.HTTP_200_OK,
    tags=["monitors"],
    summary="Send heartbeat to reset countdown",
)
async def heartbeat(
    monitor_id: str,
    store: MonitorStore = Depends(get_store),
) -> dict[str, str]:
    """Reset the monitor countdown from the beginning."""
    try:
        await store.heartbeat(monitor_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.") from None
    return {"message": "Heartbeat received; timer reset."}


@app.post(
    "/monitors/{monitor_id}/pause",
    status_code=status.HTTP_200_OK,
    tags=["monitors"],
    summary="Pause monitoring (snooze)",
)
async def pause_monitor(
    monitor_id: str,
    store: MonitorStore = Depends(get_store),
) -> dict[str, str]:
    """Pause the monitor; heartbeat resumes monitoring."""
    try:
        await store.pause(monitor_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.") from None
    return {"message": "Monitor paused; timer stopped until next heartbeat."}


@app.get(
    "/monitors",
    tags=["monitors"],
    summary="List monitors (developer's choice)",
)
async def list_monitors(
    store: MonitorStore = Depends(get_store),
    status_filter: Annotated[MonitorStatus | None, Query(alias="status")] = None,
) -> list[MonitorDetail]:
    """Return all monitors, optionally filtered by status."""
    monitors = await store.list_monitors(status_filter=status_filter)
    return [_monitor_to_detail(m) for m in monitors]


@app.get(
    "/monitors/{monitor_id}",
    tags=["monitors"],
    summary="Get monitor details (developer's choice)",
)
async def get_monitor(
    monitor_id: str,
    store: MonitorStore = Depends(get_store),
) -> MonitorDetail:
    """Return current monitor state including approximate seconds remaining."""
    mon = await store.get(monitor_id)
    if mon is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return _monitor_to_detail(mon)
