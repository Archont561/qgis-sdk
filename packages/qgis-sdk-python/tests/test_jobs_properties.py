"""Interleavings of submit, tick, cancel, worker reports and disposal (TASK-15 AC 3).

The example tests pin each rule in isolation; this state machine lets Hypothesis
interleave them and checks the guarantees that must hold in *every* order:

* a settled handle never changes state again, and a cancel request never reverts;
* every subscriber hears at most one terminal event, and it matches the status;
* nothing is delivered to a subscriber after its owner scope closed;
* a settled job with a live owner has delivered its terminal event by the end of
  the next tick - delivery is prompt, not eventual;
* after the plugin closes, every job is settled and nothing is active;
* a tick re-entered from a subscriber is a no-op and fails nothing (TASK-44);
* ``result`` and ``get()`` read the same outcome for every settled job (TASK-46);
* a settled, delivered job leaves no hook on an explicit subscription owner
  (TASK-47).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from qgis_sdk.core import JobContext, ResourceScope
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, job
from qgis_sdk.models import QgisSdkJobCancelledError, QgisSdkScopeClosedError
from qgis_sdk.testing import FakeWorkers


@dataclass(frozen=True)
class Result:
    value: int


@job(id="prop.sync", title="Sync")
def sync_echo(ctx: JobContext, value: int, reenter: bool = False) -> Result:
    """``reenter`` re-enters the host tick mid-step, as a modal dialog would."""
    ctx.progress.report(0.5)
    if reenter:
        NESTED.append(HOST_TICK[0]())
    if value < 0:
        raise ValueError("negative")
    return Result(value)


@job(id="prop.offloaded", title="Offloaded")
async def offloaded_echo(ctx: JobContext, value: int, reenter: bool = False) -> Result:
    ctx.progress.report(0.1)
    value = await ctx.require_workers().offload(lambda: value)
    if reenter:
        NESTED.append(HOST_TICK[0]())
    if value < 0:
        raise ValueError("negative")
    return Result(value)


NESTED: list[int] = []
"""What every nested tick returned, across the whole run."""

HOST_TICK: list[Callable[[], int]] = []
"""The current machine's ``jobs.tick``, for jobs that re-enter it."""


class _Tracked:
    """One handle plus what its default-owner subscriber saw."""

    def __init__(
        self,
        handle: JobHandle,
        owner: ResourceScope,
        value: int,
        *,
        reenter: Callable[[], int] | None = None,
    ) -> None:
        self.handle = handle
        self.owner = owner
        self.value = value
        self.events: list[tuple[str, object]] = []
        self.last_status = handle.status
        self.cancel_seen = handle.cancel_requested
        self.events_at_owner_close: int | None = None
        self.nested_ticks: list[int] = []

        def on_progress(fraction: float) -> None:
            self.events.append(("progress", fraction))
            if reenter is not None:
                self.nested_ticks.append(reenter())

        handle.on_progress(on_progress)
        handle.on_success(lambda result: self.events.append(("success", result)))
        handle.on_failure(lambda error: self.events.append(("failure", error)))
        handle.on_cancelled(lambda: self.events.append(("cancelled", None)))

    @property
    def terminal(self) -> list[tuple[str, object]]:
        return [event for event in self.events if event[0] != "progress"]


class JobLifetimes(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        NESTED.clear()
        HOST_TICK.clear()
        self.plugin_scope = ResourceScope()
        self.view_scope = self.plugin_scope.child()
        self.workers = FakeWorkers()
        self.jobs = JobService(
            self.plugin_scope, workers=self.workers, gui_thread=lambda: False
        )
        HOST_TICK.append(self.jobs.tick)
        self.view_jobs = self.jobs.scoped(self.view_scope)
        # A second view that only *subscribes* to other owners' jobs, so the
        # explicit-owner hooks (TASK-47) are exercised and released.
        self.listener_scope = self.plugin_scope.child()
        self.tracked: list[_Tracked] = []
        self.listener_subscribed = 0
        self.view_closed = False
        self.plugin_closed = False

    # -- rules

    @precondition(lambda self: not self.plugin_closed)
    @rule(
        view_owned=st.booleans(),
        offloaded=st.booleans(),
        value=st.integers(min_value=-1, max_value=3),
        reenters=st.booleans(),
        listened=st.booleans(),
    )
    def submit(
        self,
        view_owned: bool,
        offloaded: bool,
        value: int,
        reenters: bool,
        listened: bool,
    ) -> None:
        if view_owned and self.view_closed:
            view_owned = False
        service = self.view_jobs if view_owned else self.jobs
        owner = self.view_scope if view_owned else self.plugin_scope
        function = offloaded_echo if offloaded else sync_echo
        reenter = self.jobs.tick if reenters else None
        handle = service.bind(function).delay(value=value, reenter=reenters)
        self.tracked.append(_Tracked(handle, owner, value, reenter=reenter))
        if listened and not self.listener_scope.closed:
            handle.on_success(lambda result: None, owner=self.listener_scope)
            self.listener_subscribed += 1

    @rule()
    def tick(self) -> None:
        self.jobs.tick()
        for tracked in self.tracked:
            if tracked.handle.status.settled and not tracked.handle.owner_closed:
                assert len(tracked.terminal) == 1, tracked.handle

    @precondition(lambda self: self.tracked)
    @rule(data=st.data())
    def cancel(self, data: st.DataObject) -> None:
        tracked = data.draw(st.sampled_from(self.tracked))
        was_active = not tracked.handle.status.settled
        assert tracked.handle.cancel() == (was_active and not tracked.cancel_seen)
        assert tracked.handle.cancel_requested is True
        tracked.cancel_seen = True

    @rule()
    def worker_reports(self) -> None:
        self.workers.run_one()

    @precondition(lambda self: not self.listener_scope.closed)
    @rule()
    def close_listener(self) -> None:
        self.listener_scope.close()

    @precondition(lambda self: not self.view_closed)
    @rule()
    def close_view(self) -> None:
        self.view_scope.close()
        self.view_closed = True
        for tracked in self.tracked:
            if tracked.owner is self.view_scope:
                tracked.events_at_owner_close = len(tracked.events)
                assert tracked.handle.owner_closed is True
                assert tracked.handle.status.settled or tracked.handle.cancel_requested
                # Disposal is a cancellation request: a later explicit cancel
                # is no longer the first one.
                tracked.cancel_seen = tracked.handle.cancel_requested

    @precondition(lambda self: not self.plugin_closed)
    @rule()
    def close_plugin(self) -> None:
        self.plugin_scope.close()
        self.plugin_closed = True
        self.view_closed = True
        for tracked in self.tracked:
            if tracked.events_at_owner_close is None:
                tracked.events_at_owner_close = len(tracked.events)

    # -- invariants

    @invariant()
    def states_only_move_forward(self) -> None:
        for tracked in self.tracked:
            status = tracked.handle.status
            if tracked.last_status.settled:
                assert status is tracked.last_status
            if tracked.last_status is JobStatus.RUNNING:
                assert status is not JobStatus.QUEUED
            tracked.last_status = status
            if tracked.cancel_seen:
                assert tracked.handle.cancel_requested is True

    @invariant()
    def terminal_events_are_single_and_truthful(self) -> None:
        for tracked in self.tracked:
            terminal = tracked.terminal
            assert len(terminal) <= 1
            if terminal:
                kind, payload = terminal[0]
                status = tracked.handle.status
                assert status.settled
                assert (
                    kind
                    == {
                        JobStatus.SUCCEEDED: "success",
                        JobStatus.FAILED: "failure",
                        JobStatus.CANCELLED: "cancelled",
                    }[status]
                )
                if kind == "success":
                    assert payload == tracked.handle.result

    @invariant()
    def nothing_reaches_a_closed_owner(self) -> None:
        for tracked in self.tracked:
            if tracked.events_at_owner_close is not None:
                assert len(tracked.events) == tracked.events_at_owner_close

    @invariant()
    def a_nested_tick_is_a_no_op(self) -> None:
        assert all(steps == 0 for steps in NESTED)
        for tracked in self.tracked:
            assert all(steps == 0 for steps in tracked.nested_ticks)

    @invariant()
    def outcomes_are_the_jobs_own(self) -> None:
        """A settled job's outcome is what its author code decided, nothing else."""
        for tracked in self.tracked:
            handle = tracked.handle
            if handle.status is JobStatus.SUCCEEDED:
                assert handle.result == Result(tracked.value)
            elif handle.status is JobStatus.FAILED:
                error = handle.error
                if isinstance(error, QgisSdkScopeClosedError):
                    assert self.plugin_closed  # abandoned at unload
                else:
                    assert tracked.value < 0
                    assert isinstance(error, ValueError)
                    assert error.args == ("negative",)

    @invariant()
    def result_and_get_agree_once_settled(self) -> None:
        for tracked in self.tracked:
            handle = tracked.handle
            if not handle.status.settled or handle.owner_closed and self.plugin_closed:
                continue
            read = _outcome(_result_of, handle)
            assert read == _outcome(_get_of, handle)
            kind, payload = read
            if handle.status is JobStatus.SUCCEEDED:
                assert kind == "value"
            elif handle.status is JobStatus.FAILED:
                assert kind == "raised"
                assert payload[0] is type(handle.error)
            else:
                assert kind == "raised"
                assert payload[0] is QgisSdkJobCancelledError

    @invariant()
    def a_settled_job_holds_no_listener_hook(self) -> None:
        live = self.jobs._runtime.owner_hooks.get(self.listener_scope, {})
        for subscription in live:
            assert subscription.active
            assert not subscription._attempt.settled.is_set()
        # Never more than one close hook on the listener for any number of jobs.
        assert len(self.listener_scope._callbacks) <= 1

    @invariant()
    def a_closed_plugin_has_settled_everything(self) -> None:
        if self.plugin_closed:
            assert self.jobs.active == ()
            for tracked in self.tracked:
                assert tracked.handle.status.settled

    def teardown(self) -> None:
        if not self.plugin_closed:
            self.plugin_scope.close()


def _result_of(handle: JobHandle) -> object:
    return handle.result


def _get_of(handle: JobHandle) -> object:
    return handle.get(timeout=0)


def _outcome(
    read: Callable[[JobHandle], object], handle: JobHandle
) -> tuple[str, object]:
    """Normalise a value or a raised exception so two readers can be compared."""
    try:
        return ("value", read(handle))
    except Exception as error:  # noqa: BLE001 - the exception *is* the outcome
        return ("raised", (type(error), str(error)))


TestJobLifetimes = JobLifetimes.TestCase
TestJobLifetimes.settings = settings(
    max_examples=150, stateful_step_count=30, deadline=None
)
