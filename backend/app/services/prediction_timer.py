"""PredictionTimer — lightweight step-level performance timer.

Tracks elapsed time per named step in a prediction pipeline. Useful for
identifying bottlenecks and measuring the cost of each model component
(Dixon-Coles, TabularEnhancer, Weibull, etc.) across a batch run.

Typical usage:
    timer = PredictionTimer()
    timer.start("dixon_coles_fit")
    model.fit(training_data)
    timer.stop()

    timer.start("enhancer_fit")
    enhancer.fit(training_data)
    timer.stop()

    print(timer.to_dict())       # {"dixon_coles_fit": 0.345, ...}
    print(timer.total())         # 0.891
    print(timer.slowest())       # ("enhancer_fit", 0.546)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PredictionTimer:
    """Collects per-step timing for a prediction pipeline.

    Each named step captures the wall-clock time between start() and stop().
    Steps are additive — calling start("foo") twice accumulates.
    """

    steps: dict[str, float] = field(default_factory=dict)
    _current_step: str = ""
    _start: float = 0.0

    def start(self, name: str) -> None:
        """Begin timing a named step.

        If a previous step was started but not stopped (e.g. chained
        start calls), the previous step is silently abandoned.
        """
        self._current_step = name
        self._start = time.perf_counter()

    def stop(self) -> float:
        """Finish timing the current step and record elapsed seconds.

        Returns the elapsed time in seconds for the completed step.
        If no step is active, returns 0.0 and logs a warning.
        """
        if not self._current_step:
            import logging
            logging.getLogger(__name__).warning("timer.stop() called but no step is active")
            return 0.0

        elapsed = time.perf_counter() - self._start
        name = self._current_step
        self.steps[name] = self.steps.get(name, 0.0) + elapsed
        self._current_step = ""
        return elapsed

    def to_dict(self) -> dict[str, float]:
        """Return a copy of all recorded step timings."""
        return dict(self.steps)

    def total(self) -> float:
        """Return the sum of all recorded step times."""
        return sum(self.steps.values())

    def slowest(self) -> tuple[str, float]:
        """Return (name, seconds) of the slowest recorded step.

        If no steps are recorded, returns ("", 0.0).
        """
        if not self.steps:
            return ("", 0.0)
        name = max(self.steps, key=self.steps.__getitem__)
        return (name, self.steps[name])


def timed_step(timer: PredictionTimer, name: str, fn: callable, *args: Any, **kwargs: Any) -> Any:
    """Run *fn(*args, **kwargs)* wrapped with a timer step.

    Convenience wrapper that calls timer.start(name), invokes the callable,
    calls timer.stop(), then returns the callable's result.

    Parameters
    ----------
    timer : PredictionTimer
        The timer instance to record into.
    name : str
        Step name for the timer.
    fn : callable
        Function to invoke and time.
    *args, **kwargs
        Passed through to *fn*.

    Returns
    -------
    Any
        The return value of *fn*.
    """
    timer.start(name)
    result = fn(*args, **kwargs)
    timer.stop()
    return result
