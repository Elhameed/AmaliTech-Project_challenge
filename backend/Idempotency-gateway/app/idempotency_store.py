"""In-memory idempotency storage (replay only; mismatch and in-flight added later)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass

from app.models import PaymentRequest


def fingerprint_payment(payment: PaymentRequest) -> str:
    """Stable hash over canonical JSON so key ordering does not matter."""
    canonical = json.dumps(payment.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredResponse:
    request_hash: str
    status_code: int
    body: dict


class IdempotencyStore:
    """Async-safe in-memory store for idempotency replays."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, StoredResponse] = {}

    async def get(self, key: str) -> StoredResponse | None:
        async with self._lock:
            return self._records.get(key)

    async def put(self, key: str, value: StoredResponse) -> None:
        async with self._lock:
            self._records[key] = value

