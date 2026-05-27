from __future__ import annotations

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=[])
except ImportError:
    # Degraded mode — no-op limiter that passes everything through
    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            return lambda f: f
        def __getattr__(self, _name):
            return lambda *a, **kw: lambda f: f

    limiter = _NoopLimiter()  # type: ignore

RATE_LIMIT_MESSAGE = "请求过于频繁，请稍后再试"
