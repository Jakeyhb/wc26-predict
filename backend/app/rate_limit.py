from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

RATE_LIMIT_MESSAGE = "请求过于频繁，请稍后再试"

limiter = Limiter(key_func=get_remote_address, default_limits=[])
