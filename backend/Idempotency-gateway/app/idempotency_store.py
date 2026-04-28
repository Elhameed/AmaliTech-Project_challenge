"""In-memory idempotency storage with mismatch checks and in-flight coordination."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field

from app.models import PaymentRequest
from app.config import Settings


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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class IdempotencyStore:
    """Async-safe in-memory store for idempotency replay with in-flight waiting."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._locks_lock = asyncio.Lock()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._records: dict[str, InFlightRecord] = {}

    def _is_expired(self, rec: InFlightRecord, now: datetime) -> bool:
        if rec.response is None:
            return False
        if rec.expires_at is None:
            return False
        return now > rec.expires_at

    def _drop_if_expired(self, key: str, now: datetime) -> None:
        rec = self._records.get(key)
        if rec is None:
            return
        if self._is_expired(rec, now):
            del self._records[key]

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
        now = datetime.now(UTC)
        async with key_lock:
            self._drop_if_expired(key, now)
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
            rec.expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.idempotency_ttl_seconds)
            rec.done.set()
        await self._evict_if_needed()

    async def cleanup_loop(self) -> None:
        """Periodic removal of expired completed records."""
        while True:
            await asyncio.sleep(self._settings.cleanup_interval_seconds)
            await self._purge_expired()
            await self._evict_if_needed()

    async def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        async with self._locks_lock:
            keys = list(self._records.keys())
        for key in keys:
            key_lock = await self._lock_for_key(key)
            async with key_lock:
                rec = self._records.get(key)
                if rec is None:
                    continue
                if self._is_expired(rec, now):
                    del self._records[key]

    async def _evict_if_needed(self) -> None:
        max_n = self._settings.max_idempotency_records
        async with self._locks_lock:
            if len(self._records) <= max_n:
                return
            candidates: list[tuple[datetime, str]] = []
            for key, rec in self._records.items():
                if rec.response is None:
                    continue
                candidates.append((rec.created_at, key))
            candidates.sort(key=lambda x: x[0])
            overflow = len(self._records) - max_n
            to_evict = [key for _, key in candidates[:overflow]]
        for key in to_evict:
            key_lock = await self._lock_for_key(key)
            async with key_lock:
                rec = self._records.get(key)
                if rec is not None and rec.response is not None:
                    self._records.pop(key, None)

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

