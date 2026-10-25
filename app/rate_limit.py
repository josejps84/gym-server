import time
from collections.abc import Callable
from threading import Lock

WINDOW_SECONDS = 60.0


class RateLimiter:
    """Fixed one-minute windows per key, in memory.

    Each Cloud Run instance counts on its own; with 1-2 instances that is close enough.
    """

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def hit(self, key: str) -> float | None:
        """Counts a request; returns the seconds to wait if the key is over its limit."""
        if self._per_minute <= 0:
            return None
        now = self._clock()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= WINDOW_SECONDS:
                start, count = now, 0
            if count >= self._per_minute:
                return WINDOW_SECONDS - (now - start)
            self._windows[key] = (start, count + 1)
            if len(self._windows) > 10_000:
                self._forget_old(now)
        return None

    def _forget_old(self, now: float) -> None:
        self._windows = {k: v for k, v in self._windows.items() if now - v[0] < WINDOW_SECONDS}
