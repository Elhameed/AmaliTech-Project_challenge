"""FastAPI entrypoint (scaffold)."""

from fastapi import FastAPI

app = FastAPI(
    title="Pulse-Check-API",
    description="Dead man's switch: monitors with countdown timers and heartbeats.",
    version="0.1.0",
)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
