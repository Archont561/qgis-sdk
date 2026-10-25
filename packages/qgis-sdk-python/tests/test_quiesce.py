"""Quiescing a running plugin before an in-process replacement (decision-15/21).

A development reload must not dispose a scope while owned work is still
running. The scope collects the quiesce checks its owners registered - the
root ``JobService`` is one - and the plugin runtime offers the result to the
host: safe, or refused with the blockers named, and the old revision left
exactly as it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from qgis_sdk import action, plugin
from qgis_sdk.core import (
    PluginContext,
    PluginRuntime,
    PluginRuntimeState,
    QuiesceOutcome,
    ResourceScope,
)
from qgis_sdk.jobs import JobContext, JobService, job
from qgis_sdk.models import QgisSdkScopeClosedError
from qgis_sdk.testing import FakeWorkers


@dataclass
class Notes:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


@plugin(id="example.tools", title="Example tools")
class Tools:
    ctx: PluginContext

    @action(id="run", title="Run")
    def run(self, value: int) -> int:
        return value


class TestScope:
    def test_a_scope_with_nothing_registered_is_safe(self) -> None:
        outcome = ResourceScope().quiesce()

        assert outcome == QuiesceOutcome(refused=False, blockers=())
        assert outcome.safe_to_replace

    def test_registered_checks_and_children_are_combined(self) -> None:
        scope = ResourceScope()
        child = scope.child()
        scope.on_quiesce(lambda: QuiesceOutcome(refused=False, blockers=()))
        child.on_quiesce(
            lambda: QuiesceOutcome(refused=True, blockers=("job 1 is waiting",))
        )
        child.on_quiesce(lambda: QuiesceOutcome(refused=True, blockers=("job 2",)))

        outcome = scope.quiesce()

        assert outcome.refused
        assert outcome.blockers == ("job 1 is waiting", "job 2")

    def test_resume_reaches_every_registered_owner(self) -> None:
        scope = ResourceScope()
        resumed: list[str] = []
        scope.child().on_quiesce(
            lambda: QuiesceOutcome(refused=True, blockers=("x",)),
            resume=lambda: resumed.append("child"),
        )
        scope.on_quiesce(
            lambda: QuiesceOutcome(refused=False, blockers=()),
            resume=lambda: resumed.append("root"),
        )

        scope.resume()

        assert sorted(resumed) == ["child", "root"]

    def test_a_closed_scope_refuses_registration_and_reports_closed(self) -> None:
        scope = ResourceScope()
        scope.close()

        with pytest.raises(QgisSdkScopeClosedError):
            scope.on_quiesce(lambda: QuiesceOutcome(refused=False, blockers=()))
        assert scope.quiesce() == QuiesceOutcome(
            refused=True, blockers=("the scope is already closed",)
        )


@job(id="sum", title="Sum")
async def double(ctx: JobContext, value: int) -> int:
    return await ctx.require_workers().offload(lambda: value * 2)


class TestJobService:
    def test_the_root_service_registers_on_its_scope(self) -> None:
        scope = ResourceScope()
        workers = FakeWorkers()
        jobs = JobService(scope, workers=workers)
        handle = jobs.bind(double).delay(value=21)
        jobs.tick()  # the job is now waiting on the worker

        outcome = scope.quiesce()

        assert outcome.refused
        assert handle.id in outcome.blockers[0]
        assert "worker handoff" in outcome.blockers[0]

        scope.resume()
        workers.run_all()
        jobs.tick()
        assert scope.quiesce().safe_to_replace

    def test_a_view_scope_is_asked_through_its_parent(self) -> None:
        scope = ResourceScope()
        workers = FakeWorkers()
        jobs = JobService(scope, workers=workers)
        view = jobs.scoped(scope.child())
        view.bind(double).delay(value=1)
        jobs.tick()

        assert scope.quiesce().refused


class TestPluginRuntime:
    def test_a_running_plugin_without_work_is_safe_and_stays_running(self) -> None:
        context = PluginContext(notifications=Notes(), scope=ResourceScope())
        runtime = PluginRuntime(Tools, context)
        runtime.start()

        outcome = runtime.quiesce()

        assert outcome.safe_to_replace
        assert runtime.state is PluginRuntimeState.RUNNING
        assert runtime.actions["run"](2) == 2

    def test_stuck_work_refuses_and_resume_restores_the_old_revision(self) -> None:
        scope = ResourceScope()
        context = PluginContext(notifications=Notes(), scope=scope)
        runtime = PluginRuntime(Tools, context)
        runtime.start()
        workers = FakeWorkers()
        jobs = JobService(scope, workers=workers)
        jobs.bind(double).delay(value=1)
        jobs.tick()

        outcome = runtime.quiesce()

        assert outcome.refused
        assert outcome.blockers
        assert runtime.state is PluginRuntimeState.RUNNING
        runtime.resume()
        assert (
            jobs.bind(double).delay(value=2).status.value == "queued"
        )  # accepting work again

    def test_a_plugin_that_is_not_running_refuses_with_its_state(self) -> None:
        context = PluginContext(notifications=Notes(), scope=ResourceScope())
        runtime = PluginRuntime(Tools, context)

        outcome = runtime.quiesce()

        assert outcome.refused
        assert outcome.blockers == ("the plugin is not running (state new)",)
