"""Runtime configuration (env-driven for TTL and cleanup)."""

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    """Application settings."""

    idempotency_ttl_seconds: int = _int_env("IDEMPOTENCY_TTL_SECONDS", 1800)
    cleanup_interval_seconds: int = _int_env("CLEANUP_INTERVAL_SECONDS", 60)
    max_idempotency_records: int = _int_env("MAX_IDEMPOTENCY_RECORDS", 10_000)
    payment_delay_seconds: float = float(os.environ.get("PAYMENT_DELAY_SECONDS", "2"))


def load_settings() -> Settings:
    return Settings()

