"""Background scheduler: detect expired monitors and emit alerts."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from app.config import Settings
from app.store import MonitorStore

logger = logging.getLogger("pulse_check.alert")


async def scheduler_loop(store: MonitorStore, settings: Settings) -> None:
    """Wake periodically and mark overdue monitors as down."""
    try:
        while True:
            await asyncio.sleep(settings.scheduler_tick_seconds)
            await store.process_expired_monitors(emit_alert=_emit_alert)
    except asyncio.CancelledError:
        raise


def _emit_alert(monitor_id: str) -> None:
    payload = {
        "ALERT": f"Device {monitor_id} is down!",
        "time": datetime.now(UTC).isoformat(),
    }
    logger.info(json.dumps(payload))
