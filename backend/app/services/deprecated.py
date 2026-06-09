"""deprecated.py — Lightweight deprecation utility for WC26 Predict.

Usage:
    from app.services.deprecated import deprecated

    @deprecated(since="3.1", migrate_to="PredictionPipeline.from_artifacts()")
    def old_function(...):
        ...

Each call to a deprecated function emits a DeprecationWarning once per session.
"""
from __future__ import annotations

import functools
import logging
import warnings

logger = logging.getLogger(__name__)

# Track which functions have already warned (per-process, not per-call)
_warned: set[str] = set()


def deprecated(
    since: str,
    migrate_to: str,
    remove_after: str = "",
) -> callable:
    """Mark a function or class as deprecated.

    Args:
        since: Version when deprecation was added (e.g. "3.1").
        migrate_to: What to use instead (e.g. "PredictionPipeline.from_artifacts()").
        remove_after: Version when the function will be removed (e.g. "3.3").

    Each call site warns exactly once per process lifetime via DeprecationWarning.
    """
    msg_parts = [f"deprecated since V{since}"]
    if migrate_to:
        msg_parts.append(f"migrate to: {migrate_to}")
    if remove_after:
        msg_parts.append(f"will be removed after V{remove_after}")
    msg = "; ".join(msg_parts)

    def decorator(func: callable) -> callable:
        qualname = f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if qualname not in _warned:
                _warned.add(qualname)
                warnings.warn(
                    f"{qualname} is {msg}",
                    DeprecationWarning,
                    stacklevel=2,
                )
                logger.warning(f"Deprecated call: {qualname} — {msg}")
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if qualname not in _warned:
                _warned.add(qualname)
                warnings.warn(
                    f"{qualname} is {msg}",
                    DeprecationWarning,
                    stacklevel=2,
                )
                logger.warning(f"Deprecated call: {qualname} — {msg}")
            return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
