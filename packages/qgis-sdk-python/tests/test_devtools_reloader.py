"""The in-QGIS reload coordinator behind ``qgis-sdk dev`` (TASK-21).

Driven here against a fake plugin host, without QGIS: the policy is what
decision-15 and decision-21 fix - a bad revision never reaches unload, a
refused safe point leaves the old revision running, a start failure after
teardown disables visibly, and overlapping requests collapse into one reload
per generation.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from qgis_sdk.core import QuiesceOutcome
from qgis_sdk_tools.devtools.reloader import (
    ReloadCoordinator,
    ReloadReport,
    SourceWatcher,
    preflight,
)
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

PLUGIN = "field_tools"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / PLUGIN
    write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
    return root


@dataclass
class FakeHost:
    """What ``qgis.utils`` does for the coordinator, scripted."""

    load_ok: bool = True
    start_ok: bool = True
    unload_ok: bool = True
    quiesce_answers: list[QuiesceOutcome] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    active: bool = False
    resumed: int = 0
    during_unload: list[object] = field(default_factory=list)

    def available(self, name: str) -> bool:
        self.calls.append("available")
        return True

    def load(self, name: str) -> bool:
        self.calls.append("load")
        return self.load_ok

    def start(self, name: str) -> bool:
        self.calls.append("start")
        self.active = self.start_ok
        return self.start_ok

    def unload(self, name: str) -> bool:
        self.calls.append("unload")
        for hook in self.during_unload:
            hook()  # type: ignore[operator]
        self.active = False
        return self.unload_ok

    def forget(self, name: str) -> None:
        self.calls.append("forget")

    def running(self, name: str) -> bool:
        return self.active

    def quiesce(self, name: str) -> QuiesceOutcome:
        self.calls.append("quiesce")
        if self.quiesce_answers:
            return self.quiesce_answers.pop(0)
        return QuiesceOutcome(refused=False, blockers=())

    def resume(self, name: str) -> None:
        self.resumed += 1


@dataclass
class Console:
    said: list[str] = field(default_factory=list)
    notices: list[tuple[str, str]] = field(default_factory=list)

    def say(self, message: str) -> None:
        self.said.append(message)

    def notify(self, level: str, message: str) -> None:
        self.notices.append((level, message))


def coordinator(
    project: Path, host: FakeHost, console: Console, **options: object
) -> ReloadCoordinator:
    return ReloadCoordinator(
        root=project,
        plugin=PLUGIN,
        host=host,
        say=console.say,
        notify=console.notify,
        **options,  # type: ignore[arg-type]
    )


class TestPreflight:
    def test_a_clean_scaffold_passes_without_problems(self, project: Path) -> None:
        problems, warnings = preflight(project, PLUGIN)

        assert problems == []
        assert warnings == []

    def test_a_syntax_error_is_a_problem_with_its_position(self, project: Path) -> None:
        (project / PLUGIN / "broken.py").write_text("def (\n", encoding="utf-8")

        problems, _warnings = preflight(project, PLUGIN)

        assert len(problems) == 1
        assert problems[0].startswith(f"{PLUGIN}/broken.py:1:")

    def test_missing_metadata_is_a_problem_before_teardown(self, project: Path) -> None:
        metadata = project / PLUGIN / "metadata.txt"
        metadata.write_text(
            metadata.read_text(encoding="utf-8").replace("qgisMinimumVersion=", "#"),
            encoding="utf-8",
        )

        problems, _warnings = preflight(project, PLUGIN)

        assert any("META002" in problem for problem in problems)

    def test_architecture_findings_only_warn(self, project: Path) -> None:
        (project / PLUGIN / "native.py").write_text(
            "from qgis.core import QgsProject\n", encoding="utf-8"
        )

        problems, warnings = preflight(project, PLUGIN)

        assert problems == []
        assert any("QGIS001" in warning for warning in warnings)

    def test_findings_outside_the_plugin_package_do_not_block(
        self, project: Path
    ) -> None:
        (project / "tests" / "broken.py").write_text("def (\n", encoding="utf-8")

        problems, _warnings = preflight(project, PLUGIN)

        assert problems == []


class TestReload:
    def test_a_healthy_reload_unloads_then_starts_the_next_revision(
        self, project: Path
    ) -> None:
        host, console = FakeHost(), Console()
        reloader = coordinator(project, host, console)
        assert reloader.start() is True
        assert reloader.revision == 1

        report = reloader.reload()

        assert report == ReloadReport(
            generation=1, outcome="reloaded", revision=2, running=True
        )
        assert host.calls == [
            "available",
            "load",
            "start",
            "quiesce",
            "unload",
            "available",
            "load",
            "start",
        ]
        assert ("info", f"{PLUGIN} reloaded (revision 2)") in console.notices

    def test_preflight_problems_refuse_before_anything_is_touched(
        self, project: Path
    ) -> None:
        host, console = FakeHost(), Console()
        reloader = coordinator(project, host, console)
        reloader.start()
        host.calls.clear()
        (project / PLUGIN / "broken.py").write_text("def (\n", encoding="utf-8")

        report = reloader.reload()

        assert report.outcome == "refused"
        assert report.revision == 1
        assert report.running is True
        assert report.problems and "broken.py" in report.problems[0]
        assert host.calls == []
        assert any("revision 1 keeps running" in line for line in console.said)
        assert console.notices[-1][0] == "critical"

    def test_a_refused_safe_point_keeps_the_old_revision_and_names_blockers(
        self, project: Path
    ) -> None:
        host, console = FakeHost(), Console()
        stuck = QuiesceOutcome(refused=True, blockers=("job sum#1 is waiting",))
        host.quiesce_answers = [stuck] * 50
        now = [0.0]

        def clock() -> float:
            return now[0]

        def pump() -> None:
            now[0] += 0.5

        reloader = coordinator(
            project, host, console, quiesce_timeout=2.0, clock=clock, pump=pump
        )
        reloader.start()
        host.calls.clear()

        report = reloader.reload()

        assert report.outcome == "refused"
        assert report.blockers == ("job sum#1 is waiting",)
        assert report.revision == 1 and report.running is True
        assert "unload" not in host.calls
        assert host.calls.count("quiesce") == 5  # 0, 0.5, 1.0, 1.5, 2.0
        assert host.resumed == 1
        assert any("restart `qgis-sdk dev`" in line for line in console.said)
        assert ("critical", f"{PLUGIN} reload refused: job sum#1 is waiting") in (
            console.notices
        )

    def test_a_safe_point_reached_within_the_bound_proceeds(
        self, project: Path
    ) -> None:
        host, console = FakeHost(), Console()
        host.quiesce_answers = [
            QuiesceOutcome(refused=True, blockers=("job sum#1 is waiting",)),
            QuiesceOutcome(refused=False, blockers=()),
        ]
        reloader = coordinator(project, host, console, pump=lambda: None)
        reloader.start()

        report = reloader.reload()

        assert report.outcome == "reloaded"
        assert host.resumed == 0

    def test_a_start_failure_after_teardown_disables_visibly(
        self, project: Path
    ) -> None:
        host, console = FakeHost(), Console()
        reloader = coordinator(project, host, console)
        reloader.start()
        host.load_ok = False
        host.calls.clear()

        report = reloader.reload()

        assert report.outcome == "disabled"
        assert report.running is False
        assert report.revision == 1
        assert reloader.running is False
        assert host.calls == ["quiesce", "unload", "available", "load", "forget"]
        assert ("critical", f"{PLUGIN} is disabled: fix the error and Reload") in (
            console.notices
        )

        host.load_ok = True
        fixed = reloader.reload()

        assert fixed.outcome == "reloaded"
        assert fixed.revision == 2
        assert "unload" not in host.calls[5:]  # nothing to tear down this time

    def test_an_unload_failure_requires_a_restart(self, project: Path) -> None:
        host, console = FakeHost(), Console()
        reloader = coordinator(project, host, console)
        reloader.start()
        host.unload_ok = False

        report = reloader.reload()

        assert report.outcome == "disabled"
        assert "restart" in report.reason
        assert reloader.running is False

    def test_a_request_during_a_reload_is_coalesced_into_one_more(
        self, project: Path
    ) -> None:
        host, console = FakeHost(), Console()
        reloader = coordinator(project, host, console)
        reloader.start()
        inner: list[ReloadReport] = []

        def burst() -> None:  # two edits land while the first unload runs
            host.during_unload.clear()
            inner.append(reloader.reload())
            inner.append(reloader.reload())

        host.during_unload = [burst]

        report = reloader.reload()

        assert [r.outcome for r in inner] == ["coalesced", "coalesced"]
        assert report.outcome == "reloaded"
        assert report.generation == 2  # the follow-up ran once, not twice
        assert reloader.revision == 3

    def test_requests_are_debounced_through_the_scheduler(self, project: Path) -> None:
        host, console = FakeHost(), Console()
        scheduled: list[int] = []
        reloader = coordinator(
            project, host, console, schedule=lambda: scheduled.append(1)
        )
        reloader.start()

        reloader.request()
        reloader.request()

        assert scheduled == [1, 1]  # the host timer restarts; one fire follows
        assert reloader.revision == 1

    def test_reports_serialise_for_the_exercise(self, project: Path) -> None:
        report = ReloadReport(
            generation=3,
            outcome="refused",
            revision=2,
            running=True,
            blockers=("a",),
            reason="x",
        )

        assert report.as_dict() == {
            "generation": 3,
            "outcome": "refused",
            "revision": 2,
            "running": True,
            "problems": [],
            "blockers": ["a"],
            "reason": "x",
        }


class TestSourceWatcher:
    def test_sees_python_and_metadata_changes_once(self, project: Path) -> None:
        changes: list[int] = []
        watcher = SourceWatcher(project, PLUGIN, on_change=lambda: changes.append(1))

        assert watcher.poll() is False
        source = project / PLUGIN / "plugin.py"
        source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        _bump(source)

        assert watcher.poll() is True
        assert watcher.poll() is False
        assert changes == [1]

    def test_new_and_removed_files_count(self, project: Path) -> None:
        watcher = SourceWatcher(project, PLUGIN, on_change=lambda: None)
        extra = project / PLUGIN / "extra.py"
        extra.write_text("x = 1\n", encoding="utf-8")

        assert watcher.poll() is True
        extra.unlink()
        assert watcher.poll() is True

    def test_ignores_web_sources_caches_and_other_files(self, project: Path) -> None:
        watcher = SourceWatcher(project, PLUGIN, on_change=lambda: None)
        (project / PLUGIN / "web").mkdir()
        (project / PLUGIN / "web" / "main.ts").write_text("", encoding="utf-8")
        (project / PLUGIN / "__pycache__").mkdir()
        (project / PLUGIN / "__pycache__" / "x.pyc").write_text("", encoding="utf-8")
        (project / PLUGIN / "notes.md").write_text("", encoding="utf-8")
        (project / "tests" / "test_more.py").write_text("", encoding="utf-8")

        assert watcher.poll() is False

    def test_resync_forgets_edits_made_while_paused(self, project: Path) -> None:
        watcher = SourceWatcher(project, PLUGIN, on_change=lambda: None)
        (project / PLUGIN / "extra.py").write_text("x = 1\n", encoding="utf-8")

        watcher.resync()

        assert watcher.poll() is False


def _bump(path: Path) -> None:
    """Move the mtime forward so a same-second rewrite is still a change."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    time.sleep(0)
