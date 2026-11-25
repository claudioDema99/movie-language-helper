"""Private-deployment authentication and bounded fixed-window rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from threading import Lock


@dataclass(slots=True)
class _Window:
    started_at: int
    count: int


class FixedWindowRateLimiter:
    """Process-local limiter suitable only for the enforced one-process profile."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    def check(self, key: str, now: float | None = None) -> int | None:
        current = int(time.time() if now is None else now)
        window_start = current - current % self._window_seconds
        with self._lock:
            window = self._windows.get(key)
            if window is None or window.started_at != window_start:
                self._windows[key] = _Window(window_start, 1)
                return None
            if window.count >= self._limit:
                return window_start + self._window_seconds - current
            window.count += 1
            return None


def bearer_token(header: str | None) -> str | None:
    if header is None or not header.startswith("Bearer "):
        return None
    token = header.removeprefix("Bearer ")
    return token if token else None


def token_matches(candidate: str | None, expected: str) -> bool:
    return candidate is not None and hmac.compare_digest(candidate, expected)


def client_key(forwarded_for: str | None, peer: str) -> str:
    """Hash the edge-proxy client address without retaining it as a label."""
    value = (forwarded_for or "").split(",", maxsplit=1)[0].strip() or peer
    return hashlib.sha256(value.encode()).hexdigest()
