"""FastAPI entrypoint (scaffold)."""

from fastapi import FastAPI

app = FastAPI(
    title="Idempotency-Gateway",
    description='Pay-once protocol: POST /process-payment with "Idempotency-Key" header.',
    version="0.1.0",
)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""
    return {"status": "ok"}

