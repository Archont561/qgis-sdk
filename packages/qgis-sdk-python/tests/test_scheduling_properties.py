"""Property tests for interleaved scheduling actions on one owner scope.

Cancellation, worker reports, ticks and disposal can arrive in any order. These
properties pin the guarantees the runtime relies on regardless of that order:
a settled job never resumes, a disposed scope never delivers work to author code,
and draining a reported job always settles it.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st
from qgis_sdk.core import Handoff, JobState, ResourceScope, StepScheduler


def _interleaved_scheduling_actions_never_phase1(resumed, resumed_at_close, scope):
    if resumed_at_close is not None:
        assert len(resumed) == resumed_at_close, (
            "a disposed scope delivered author code"
        )

    # Dispose so queued coroutines are closed rather than left for the GC to warn about.
    scope.close()


SETTLED = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}

action_strategy = st.sampled_from(["tick", "resolve", "fail", "cancel", "close"])


@dataclass
class _Interleaved:
    """The mutable state one interleaved scheduling property drives."""

    scheduler: StepScheduler
    scope: ResourceScope
    jobs: list
    handoffs: list[Handoff]
    resumed: list[int]
    seen_settled: dict[int, JobState]
    resumed_at_close: int | None = None


def _close_action(state: _Interleaved) -> None:
    state.scope.close()
    state.resumed_at_close = len(state.resumed)


def _tick_action(state: _Interleaved) -> None:
    state.scheduler.tick()


def _resolve_action(state: _Interleaved) -> None:
    for handoff in state.handoffs:
        handoff.resolve("report")


def _fail_action(state: _Interleaved) -> None:
    for handoff in state.handoffs:
        handoff.fail(RuntimeError("worker failed"))


def _cancel_action(state: _Interleaved) -> None:
    for job in state.jobs:
        job.cancel()


_ACTION_HANDLERS = {
    "close": _close_action,
    "tick": _tick_action,
    "resolve": _resolve_action,
    "fail": _fail_action,
    "cancel": _cancel_action,
}


def _assert_settled_stays(state: _Interleaved) -> None:
    """No job leaves a settled state, however the actions are interleaved."""
    for job in state.jobs:
        if job.state in SETTLED:
            previous = state.seen_settled.setdefault(job.id, job.state)
            assert previous is job.state, f"job {job.id} left its settled state"
        else:
            assert job.id not in state.seen_settled


def _interleaved_state(job_count: int) -> _Interleaved:
    """Submit ``job_count`` suspended bodies over one owner scope."""
    scope = ResourceScope()
    scheduler = StepScheduler(scope)
    resumed: list[int] = []
    handoffs = [Handoff() for _ in range(job_count)]

    async def body(index: int, handoff: Handoff) -> str:
        await handoff
        resumed.append(index)
        return "done"

    jobs = [
        scheduler.submit(body(index, handoffs[index])) for index in range(job_count)
    ]
    return _Interleaved(scheduler, scope, jobs, handoffs, resumed, {})


@given(
    actions=st.lists(action_strategy, min_size=0, max_size=24),
    job_count=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=120, deadline=None)
def test_interleaved_scheduling_actions_never_resurrect_or_deliver_late_work(
    actions: list[str], job_count: int
) -> None:
    state = _interleaved_state(job_count)
    for action in actions:
        _ACTION_HANDLERS[action](state)
        _assert_settled_stays(state)
    _interleaved_scheduling_actions_never_phase1(
        state.resumed, state.resumed_at_close, state.scope
    )


@given(pending=st.integers(min_value=1, max_value=6))
@settings(max_examples=30, deadline=None)
def test_a_reported_job_always_drains_to_a_settled_state(pending: int) -> None:
    scope = ResourceScope()
    scheduler = StepScheduler(scope)
    handoffs = [Handoff() for _ in range(pending)]

    async def body(handoff: Handoff, label: str) -> str:
        await handoff
        return label

    jobs = [
        scheduler.submit(body(handoff, f"job-{index}"))
        for index, handoff in enumerate(handoffs)
    ]
    for index, handoff in enumerate(handoffs):
        if index % 2:
            handoff.fail(RuntimeError("worker failed"))
        else:
            handoff.resolve("report")

    assert scheduler.drain(max_ticks=pending + 2) == 1
    assert scheduler.jobs == {}
    for index, job in enumerate(jobs):
        if index % 2:
            assert job.state is JobState.FAILED
            assert isinstance(job.error, RuntimeError)
        else:
            assert job.state is JobState.COMPLETED
            assert job.result == f"job-{index}"
