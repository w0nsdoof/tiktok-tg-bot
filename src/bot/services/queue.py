import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog

log = structlog.get_logger()


class DownloadQueue:
    def __init__(self, max_concurrent: int = 3) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent
        self._active = 0

    @property
    def is_full(self) -> bool:
        return self._active >= self._max

    @property
    def active_count(self) -> int:
        return self._active

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        if self.is_full:
            log.info("queue.full", queue_depth=self._active)
        await self._semaphore.acquire()
        self._active += 1
        log.info("queue.acquired", current_active=self._active)
        try:
            yield
        finally:
            self._active -= 1
            self._semaphore.release()
            log.info("queue.released", current_active=self._active)
