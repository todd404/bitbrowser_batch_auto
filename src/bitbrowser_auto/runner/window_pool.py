from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class WindowSlotPool:
    max_concurrent_windows: int
    _busy: set[str] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self, browser_id: str) -> bool:
        async with self._lock:
            if browser_id in self._busy:
                return False
            if len(self._busy) >= self.max_concurrent_windows:
                return False
            self._busy.add(browser_id)
            return True

    async def release(self, browser_id: str) -> None:
        async with self._lock:
            self._busy.discard(browser_id)

    async def busy_browser_ids(self) -> set[str]:
        async with self._lock:
            return set(self._busy)

    async def running_count(self) -> int:
        async with self._lock:
            return len(self._busy)

