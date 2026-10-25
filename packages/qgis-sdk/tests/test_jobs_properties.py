"""Interleavings of submit, tick, cancel, worker reports and disposal (TASK-15 AC 3).

The example tests pin each rule in isolation; this state machine lets Hypothesis
interleave them and checks the guarantees that must hold in *every* order:

* a settled handle never changes state again, and a cancel request never reverts;
* every subscriber hears at most one terminal event, and it matches the status;
* nothing is delivered to a subscriber after its owner scope closed;
* a settled job with a live owner has delivered its terminal event by the end of
  the next tick - delivery is prompt, not eventual;
* after the plugin closes, every job is settled and nothing is active.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from qgis_sdk.core import JobContext, ResourceScope
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, job
from qgis_sdk.testing import FakeWorkers


@dataclass(frozen=True)
class Inputs:
    value: int


@dataclass(frozen=True)
class Result:
    value: int


@job(id="prop.sync", title="Sync")
class Sync:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    def run(self, inputs: Inputs) -> Result:
        self.ctx.progress.report(0.5)
        if inputs.value < 0:
            raise ValueError("negative")
        return Result(inputs.value)


@job(id="prop.offloaded", title="Offloaded")
class Offloaded:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    async def run(self, inputs: Inputs) -> Result:
        self.ctx.progress.report(0.1)
        value = await self.ctx.require_workers().offload(lambda: inputs.value)
        if value < 0:
            raise ValueError("negative")
        return Result(value)


class _Tracked:
    """One handle plus what its default-owner subscriber saw."""

    def __init__(self, handle: JobHandle, owner: ResourceScope) -> None:
        self.handle = handle
        self.owner = owner
        self.events: list[tuple[str, object]] = []
        self.last_status = handle.status
        self.cancel_seen = handle.cancel_requested
        self.events_at_owner_close: int | None = None
        handle.on_progress(lambda fraction: self.events.append(("progress", fraction)))
        handle.on_success(lambda result: self.events.append(("success", result)))
        handle.on_failure(lambda error: self.events.append(("failure", error)))
        handle.on_cancelled(lambda: self.events.append(("cancelled", None)))

    @property
    def terminal(self) -> list[tuple[str, object]]:
        return [event for event in self.events if event[0] != "progress"]


class JobLifetimes(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.plugin_scope = ResourceScope()
        self.view_scope = self.plugin_scope.child()
        self.workers = FakeWorkers()
        self.jobs = JobService(
            self.plugin_scope, workers=self.workers, gui_thread=lambda: False
        )
        self.view_jobs = self.jobs.scoped(self.view_scope)
        self.tracked: list[_Tracked] = []
        self.view_closed = False
        self.plugin_closed = False

    # -- rules

    @precondition(lambda self: not self.plugin_closed)
    @rule(
        view_owned=st.booleans(),
        offloaded=st.booleans(),
        value=st.integers(min_value=-1, max_value=3),
    )
    def submit(self, view_owned: bool, offloaded: bool, value: int) -> None:
        if view_owned and self.view_closed:
            view_owned = False
        service = self.view_jobs if view_owned else self.jobs
        owner = self.view_scope if view_owned else self.plugin_scope
        cls = Offloaded if offloaded else Sync
        handle = service.bind(cls).delay(Inputs(value))
        self.tracked.append(_Tracked(handle, owner))

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
    def a_closed_plugin_has_settled_everything(self) -> None:
        if self.plugin_closed:
            assert self.jobs.active == ()
            for tracked in self.tracked:
                assert tracked.handle.status.settled

    def teardown(self) -> None:
        if not self.plugin_closed:
            self.plugin_scope.close()


TestJobLifetimes = JobLifetimes.TestCase
TestJobLifetimes.settings = settings(
    max_examples=150, stateful_step_count=30, deadline=None
)
