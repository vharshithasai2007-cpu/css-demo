"""Small in-memory rate limiter for portal register/login attempts.

Keys are (action, client IP, normalized email), so register and login do not
consume each other's budget. Tests can call reset_rate_limit() between cases.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60

_attempts: dict[tuple[str, str, str], deque[float]] = {}
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _key(request: Request, email: str, action: str) -> tuple[str, str, str]:
    return (action, _client_ip(request), email.strip().lower())


def check_rate_limit(request: Request, email: str, action: str) -> None:
    """Record an attempt or raise 429 once the per-minute budget is spent."""

    now = time.monotonic()
    key = _key(request, email, action)

    with _lock:
        bucket = _attempts.setdefault(key, deque())
        while bucket and now - bucket[0] >= RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT_ATTEMPTS:
            retry_after = max(
                1,
                int(RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])),
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)


def reset_rate_limit() -> None:
    """Clear all in-memory counters (used by tests and local demos)."""

    with _lock:
        _attempts.clear()
