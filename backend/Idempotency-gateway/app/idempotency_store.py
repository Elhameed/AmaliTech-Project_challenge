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

    async def get_if_match(self, key: str, request_hash: str) -> StoredResponse | None:
        """
        Return stored response if key exists and request hash matches.

        Returns None if key missing. Raises ValueError if key exists but hash differs.
        """
        async with self._lock:
            existing = self._records.get(key)
            if existing is None:
                return None
            if existing.request_hash != request_hash:
                raise ValueError("idempotency_key_reused_with_different_body")
            return existing

