"""A scripted ``Workers`` for job tests: the test decides when work completes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis_sdk.core.scheduling import Handoff


class FakeWorkers:
    """Queue offloaded callables and run them only when the test says so.

    ``offload`` returns the :class:`~qgis_sdk.core.scheduling.Handoff` the job
    suspends on; :meth:`run_one`/:meth:`run_all` execute the callables on the
    calling thread - a test may well call them from a helper thread to prove a
    report never reaches a subscriber from there. ``cancelled`` counts how
    often a job cancelled while suspended told the (fake) worker about it.
    """

    def __init__(self) -> None:
        self._pending: list[tuple[Callable[[], Any], Handoff]] = []
        self.cancelled = 0

    @property
    def pending(self) -> int:
        """How many offloaded callables have not run yet."""
        return len(self._pending)

    def offload(self, fn: Callable[[], Any]) -> Handoff:
        """Queue ``fn``; the job suspends on the returned handoff."""
        handoff = Handoff(on_cancel=self._cancel)
        self._pending.append((fn, handoff))
        return handoff

    def run_one(self) -> bool:
        """Run the oldest pending callable; return whether there was one."""
        if not self._pending:
            return False
        fn, handoff = self._pending.pop(0)
        try:
            handoff.resolve(fn())
        except BaseException as error:  # noqa: BLE001 - the worker reports, never raises
            handoff.fail(error)
        return True

    def run_all(self) -> int:
        """Run every pending callable in order; return how many ran."""
        count = 0
        while self.run_one():
            count += 1
        return count

    def _cancel(self) -> None:
        self.cancelled += 1
