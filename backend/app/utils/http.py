from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.logging import get_logger

logger = get_logger(__name__)


class AsyncRateLimiter:
    def __init__(self, calls_per_minute: int) -> None:
        self._interval = 60.0 / max(1, calls_per_minute)
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            sleep_for = self._interval - (now - self._last_call)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            self._last_call = loop.time()


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout: float = 30.0,
    attempts: int = 3,
) -> Any:
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPError, ValueError)),
            reraise=True,
        ):
            with attempt:
                response = await client.get(url, headers=headers, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
    except RetryError as exc:
        logger.exception("HTTP JSON fetch failed after retries: %s", url)
        raise exc.last_attempt.exception()

