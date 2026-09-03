"""Bounded in-process admission control for the public answer endpoint."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Literal


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admitted: bool
    reason: Literal["admitted", "rate_limited", "capacity_exceeded"]
    retry_after_seconds: int = 0


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    """Thread-safe per-client and global quotas with bounded client state."""

    def __init__(
        self,
        *,
        per_client_limit: int,
        global_limit: int,
        window_seconds: int,
        max_clients: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if min(per_client_limit, global_limit, window_seconds, max_clients) < 1:
            raise ValueError("rate limiter values must be positive")
        if global_limit < per_client_limit:
            raise ValueError("global limit cannot be lower than the per-client limit")
        self._per_client_limit = per_client_limit
        self._global_limit = global_limit
        self._window_seconds = window_seconds
        self._max_clients = max_clients
        self._clock = clock
        self._lock = Lock()
        self._global_window = _Window(started_at=clock(), count=0)
        self._clients: OrderedDict[str, _Window] = OrderedDict()

    @property
    def tracked_client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def admit(self, client_key: str) -> AdmissionDecision:
        now = self._clock()
        with self._lock:
            self._reset_global_if_expired(now)
            global_wait = self._retry_after(self._global_window, now)

            if self._global_window.count >= self._global_limit:
                return AdmissionDecision(False, "rate_limited", global_wait)

            client_window = self._client_window(client_key, now)
            client_wait = self._retry_after(client_window, now)
            if client_window.count >= self._per_client_limit:
                return AdmissionDecision(False, "rate_limited", client_wait)

            self._global_window.count += 1
            client_window.count += 1
            return AdmissionDecision(True, "admitted")

    def _reset_global_if_expired(self, now: float) -> None:
        if now - self._global_window.started_at >= self._window_seconds:
            self._global_window = _Window(started_at=now, count=0)

    def _client_window(self, client_key: str, now: float) -> _Window:
        existing = self._clients.pop(client_key, None)
        if existing is None or now - existing.started_at >= self._window_seconds:
            existing = _Window(started_at=now, count=0)
        self._clients[client_key] = existing
        while len(self._clients) > self._max_clients:
            self._clients.popitem(last=False)
        return existing

    def _retry_after(self, window: _Window, now: float) -> int:
        remaining = self._window_seconds - (now - window.started_at)
        return max(1, ceil(remaining))


class PublicRequestGuard:
    """Combine request quotas with a non-blocking in-flight work cap."""

    def __init__(
        self,
        *,
        per_client_limit: int,
        global_limit: int,
        window_seconds: int,
        max_clients: int,
        max_concurrent: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max concurrent requests must be positive")
        self._rate_limiter = FixedWindowRateLimiter(
            per_client_limit=per_client_limit,
            global_limit=global_limit,
            window_seconds=window_seconds,
            max_clients=max_clients,
            clock=clock,
        )
        self._capacity = BoundedSemaphore(max_concurrent)

    @property
    def tracked_client_count(self) -> int:
        return self._rate_limiter.tracked_client_count

    def admit(self, client_key: str) -> AdmissionDecision:
        rate_decision = self._rate_limiter.admit(client_key)
        if not rate_decision.admitted:
            return rate_decision
        if not self._capacity.acquire(blocking=False):
            return AdmissionDecision(False, "capacity_exceeded", 1)
        return AdmissionDecision(True, "admitted")

    def release(self) -> None:
        self._capacity.release()
