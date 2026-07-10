import asyncio
from types import TracebackType

from fastapi import HTTPException, status


class CapacityLimiter:
    """Bounds how many requests may hold a slot concurrently"""

    def __init__(self, max_concurrent: int, wait_timeout: float) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._wait_timeout = wait_timeout

    async def __aenter__(self) -> None:
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self._wait_timeout
            )
        except TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server is at capacity, please retry shortly",
            ) from None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._semaphore.release()
