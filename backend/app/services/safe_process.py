"""Safe subprocess execution for long-running model fits.

The Weibull model (penaltyblog WeibullCopulaGoalsModel.fit) can hang or take
excessively long on certain datasets. This module wraps arbitrary callables
in a subprocess with a strict timeout, so the main process can recover cleanly.

On Windows (spawn mode), *fn* must be a module-level callable (function, class,
or bound method defined in an importable module). Lambdas and functions defined
inside ``if __name__ == "__main__"`` blocks cannot be pickled and will fail.
On Linux/macOS (fork mode) any callable is accepted.

Typical usage:
    result = run_in_process_with_timeout(
        model.fit,
        args=(df,),
        timeout_s=120,
    )
    if result["ok"]:
        logger.info(f"Fit succeeded: {result['result']}")
    else:
        logger.warning(f"Fit failed/timed out: {result['error']}")
"""

from __future__ import annotations

import logging
import traceback
from multiprocessing import Process, Queue
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _worker(
    fn: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    result_queue: Queue,
    error_queue: Queue,
) -> None:
    """Module-level target for multiprocessing.Process.

    Defined at module scope so it is picklable on Windows (spawn mode).
    """
    try:
        output = fn(*args, **kwargs)
        result_queue.put(output)
        error_queue.put("")
    except Exception as exc:
        result_queue.put(None)
        error_queue.put(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")


def run_in_process_with_timeout(
    fn: Callable[..., Any],
    args: tuple = (),
    kwargs: dict | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Run *fn* in a separate subprocess with a wall-clock timeout.

    If the function does not complete within *timeout_s* seconds, the
    subprocess is terminated and a timeout error is returned. This is
    primarily used for the Weibull model fit which can hang on certain
    datasets.

    Parameters
    ----------
    fn : Callable
        The function to execute in the subprocess.
    args : tuple
        Positional arguments to pass to *fn*.
    kwargs : dict | None
        Keyword arguments to pass to *fn*.
    timeout_s : int
        Maximum wall-clock seconds to wait before terminating. Default 120.

    Returns
    -------
    dict
        Always returns a dict with keys:
        - "ok": bool — True if the function completed before timeout.
        - "result": Any — the return value of *fn*, or None on failure.
        - "error": str — empty string on success, error message otherwise.
    """
    if kwargs is None:
        kwargs = {}

    result_queue: Queue = Queue()
    error_queue: Queue = Queue()

    process = Process(
        target=_worker,
        args=(fn, args, kwargs, result_queue, error_queue),
        daemon=True,
    )
    process.start()
    logger.info(
        "Process started for %s (pid=%d, timeout=%ds)",
        getattr(fn, "__name__", str(fn)),
        process.pid,
        timeout_s,
    )

    process.join(timeout=timeout_s)

    if process.is_alive():
        # Timeout — kill the process and return error
        logger.warning(
            "Process timed out after %ds — terminating pid=%d",
            timeout_s,
            process.pid,
        )
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
        return {"ok": False, "result": None, "error": f"Process timed out after {timeout_s}s"}

    # Process finished — collect result
    try:
        result = result_queue.get_nowait()
    except Exception:
        result = None
    try:
        error = error_queue.get_nowait()
    except Exception:
        error = "Unknown error — result queue empty"

    ok = not bool(error) and result is not None
    if not ok:
        logger.error("Process failed for %s: %s", getattr(fn, "__name__", str(fn)), error[:200])

    return {"ok": ok, "result": result, "error": error}
