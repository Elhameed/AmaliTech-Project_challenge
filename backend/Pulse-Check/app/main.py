"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from app.config import Settings, load_settings
from app.models import MonitorCreate, MonitorRegisterResponse
from app.store import DuplicateMonitorError, MonitorStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = load_settings()
    app.state.store = MonitorStore()
    yield


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
