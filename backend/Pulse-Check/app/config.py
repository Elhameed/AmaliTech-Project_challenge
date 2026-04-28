"""Runtime configuration."""

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    """Application settings (scheduler added in a later commit)."""

    scheduler_tick_seconds: float = _float_env("SCHEDULER_TICK_SECONDS", 1.0)


def load_settings() -> Settings:
    return Settings()
