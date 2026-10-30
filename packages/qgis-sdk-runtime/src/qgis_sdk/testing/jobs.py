"""A scripted ``Workers`` for job tests: the test decides when work completes."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_futures
from typing import Any

from qgis_sdk.core.scheduling import Handoff
from qgis_sdk.services import WorkItem


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
        self.items: list[WorkItem] = []
        self.cancelled = 0

    @property
    def pending(self) -> int:
        """How many offloaded callables have not run yet."""
        return len(self._pending)

    def offload(
        self, fn: Callable[[], Any], *, item: WorkItem | None = None
    ) -> Handoff:
        """Queue ``fn``; the job suspends on the returned handoff.

        ``item`` is what a real backend would show: this one records it in
        ``items`` so a test can assert the job reached it with its title.
        """
        if item is not None:
            self.items.append(item)
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


class ThreadWorkers:
    """A real worker pool: the evidence the worker-first contract asks for.

    ``FakeWorkers`` runs a callable when the *test* says so, on the thread
    calling it, which is what makes delivery and ownership observable. This one
    runs it on a thread of its own, so a test can prove the body never ran on
    the driving thread and that the tick stayed free while it ran. ``thread_ids``
    records where each callable ran; ``wait`` blocks until every pending one
    finished, for a test that wants a deterministic join.
    """

    def __init__(self, *, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="qgis-sdk-worker"
        )
        self._pending: set[Future[Any]] = set()
        self.items: list[WorkItem] = []
        self.thread_ids: list[int] = []
        self.cancelled = 0

    def offload(
        self, fn: Callable[[], Any], *, item: WorkItem | None = None
    ) -> Handoff:
        """Queue ``fn`` on a worker thread; the job suspends on the handoff."""
        if item is not None:
            self.items.append(item)
        handoff = Handoff(on_cancel=self._cancel)
        future = self._pool.submit(self._run, fn, handoff)
        self._pending.add(future)
        return handoff

    def _run(self, fn: Callable[[], Any], handoff: Handoff) -> None:
        self.thread_ids.append(threading.get_ident())
        try:
            handoff.resolve(fn())
        except BaseException as error:  # noqa: BLE001 - a worker reports, never raises
            handoff.fail(error)

    def _cancel(self) -> None:
        self.cancelled += 1

    @property
    def pending(self) -> int:
        """How many callables are still running."""
        return len(self._pending)

    def wait(self, timeout: float = 10.0) -> None:
        """Block until every submitted callable finished."""
        done, _ = wait_futures(tuple(self._pending), timeout=timeout)
        self._pending -= set(done)

    def close(self) -> None:
        """Stop the pool; a test calls this, the runtime never does."""
        self._pool.shutdown(wait=True)
