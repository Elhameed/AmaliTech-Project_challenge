"""In-memory idempotency storage with mismatch checks and in-flight coordination."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field

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


@dataclass
class InFlightRecord:
    request_hash: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    response: StoredResponse | None = None


class IdempotencyStore:
    """Async-safe in-memory store for idempotency replay with in-flight waiting."""

    def __init__(self) -> None:
        self._locks_lock = asyncio.Lock()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._records: dict[str, InFlightRecord] = {}

    async def _lock_for_key(self, key: str) -> asyncio.Lock:
        async with self._locks_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._key_locks[key] = lock
            return lock

    async def decide(self, key: str, request_hash: str) -> tuple[str, InFlightRecord]:
        """
        Coordinate a request under a key.

        Returns (kind, record) where kind is:
        - \"owner\": caller should process and then call complete()
        - \"waiter\": caller should wait for record.done and then read record.response
        - \"replay\": caller can return record.response immediately

        Raises ValueError if key exists but request_hash differs.
        """
        key_lock = await self._lock_for_key(key)
        async with key_lock:
            rec = self._records.get(key)
            if rec is None:
                rec = InFlightRecord(request_hash=request_hash)
                self._records[key] = rec
                return "owner", rec

            if rec.request_hash != request_hash:
                raise ValueError("idempotency_key_reused_with_different_body")

            if rec.response is not None:
                return "replay", rec

            return "waiter", rec

    async def complete(self, key: str, response: StoredResponse) -> None:
        """Finalize the in-flight record and wake all waiters."""
        key_lock = await self._lock_for_key(key)
        async with key_lock:
            rec = self._records.get(key)
            if rec is None:
                rec = InFlightRecord(request_hash=response.request_hash)
                self._records[key] = rec
            rec.response = response
            rec.done.set()

    async def get_if_match(self, key: str, request_hash: str) -> StoredResponse | None:
        """
        Backwards compatible helper: return response if completed and hash matches.

        Returns None if key missing/not completed. Raises ValueError if key exists but hash differs.
        """
        kind, rec = await self.decide(key, request_hash)
        if kind == "replay":
            assert rec.response is not None
            return rec.response
        if kind == "owner":
            return None
        # waiter: caller should use decide() to wait; this keeps old signature safe.
        return None

