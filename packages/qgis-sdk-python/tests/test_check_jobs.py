"""JOB001 / JOB002 / JOB003: a job body that cannot run on a worker (TASK-117).

The rules read the source only (decision-8) and report what a ``@job`` body
does that a worker thread must not: GUI state (``JOB001``), a context
attribute a ``WorkerContext`` refuses (``JOB002``) and a by-name import the
check cannot follow (``JOB003``, a warning). They are early feedback, not a
proof of thread safety - the runtime capability guard covers the captured
reference a source check cannot see (decision-69).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.check.jobs import check_jobs
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

runner = CliRunner()

PYPROJECT = """[project]
name = "field-tools"
version = "0.1.0"
description = "Field tools."
authors = [{ name = "Jane", email = "jane@example.org" }]
dependencies = ["qgis-sdk-runtime>=0.1,<99"]

[tool.qgis-sdk]
plugin = "field_tools.plugin:app"
qgis-minimum-version = "3.40"
"""


def found(source: str):
    return list(check_jobs(textwrap.dedent(source), path=Path("field_tools/plugin.py")))


def rules(source: str) -> list[tuple[str, str]]:
    return [(d.rule, d.severity) for d in found(source)]


def messages(source: str) -> list[str]:
    return [d.message for d in found(source)]


# -- JOB001: GUI state reached from a job body -------------------------------------


def test_the_interface_imported_at_module_level_is_a_finding() -> None:
    source = """
        from qgis.utils import iface
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job(id="demo.load", title="Load")
        def load(ctx: WorkerContext, path: str) -> int:
            iface.mapCanvas().refresh()
            return 1
        """

    assert rules(source) == [("JOB001", "error")]
    assert "job `load` reaches `qgis.utils.iface`" in messages(source)[0]


def test_a_gui_class_imported_under_an_alias_is_a_finding() -> None:
    source = """
        from qgis.gui import QgsMapCanvas as Canvas
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def draw(ctx: WorkerContext) -> None:
            Canvas().show()
        """

    assert rules(source) == [("JOB001", "error")]
    assert "`qgis.gui.QgsMapCanvas`" in messages(source)[0]


def test_a_module_level_binding_that_holds_gui_state_is_named_with_its_source() -> None:
    source = """
        from qgis.gui import QgsMapCanvas
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        canvas = QgsMapCanvas()

        @job()
        def redraw(ctx: WorkerContext) -> None:
            canvas.refresh()
        """

    assert rules(source) == [("JOB001", "error")]
    assert "reaches `canvas` (bound to `qgis.gui.QgsMapCanvas`)" in messages(source)[0]


def test_the_live_project_is_a_finding_however_it_is_spelled() -> None:
    source = """
        from qgis.core import QgsProject
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def count(ctx: WorkerContext) -> int:
            return len(QgsProject.instance().mapLayers())
        """

    assert rules(source) == [("JOB001", "error")]
    assert "`qgis.core.QgsProject.instance`" in messages(source)[0]


def test_an_interface_imported_inside_the_body_is_a_finding_too() -> None:
    source = """
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def refresh(ctx: WorkerContext) -> None:
            from qgis.utils import iface

            iface.mapCanvas().refresh()
        """

    assert rules(source) == [("JOB001", "error")]
    assert "`iface` (bound to `qgis.utils.iface`)" in messages(source)[0]


# -- JOB002: a context attribute a WorkerContext refuses ---------------------------


def test_a_driving_thread_capability_read_from_a_job_is_a_finding() -> None:
    source = """
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def load(ctx: WorkerContext) -> int:
            return len(ctx.layers.layer_ids())
        """

    assert rules(source) == [("JOB002", "error")]
    assert "reads `ctx.layers`" in messages(source)[0]
    assert "a WorkerContext refuses" in messages(source)[0]


def test_progress_and_cancellation_are_the_whole_job_context() -> None:
    source = """
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def load(ctx: WorkerContext, ids: tuple[str, ...]) -> int:
            for index, item in enumerate(ids):
                if ctx.cancellation.is_cancelled():
                    return index
                ctx.progress.set(index / len(ids))
            return len(ids)
        """

    assert found(source) == []


# -- what the check must not report (AC2: no blanket bans) --------------------------


def test_a_local_binding_shadows_the_module_level_one() -> None:
    source = """
        from qgis.utils import iface
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def ok(ctx: WorkerContext, iface: str) -> int:
            iface = iface.strip()
            return len(iface)
        """

    assert found(source) == []


def test_a_global_declaration_brings_the_module_binding_back() -> None:
    source = """
        from qgis.utils import iface
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def ok(ctx: WorkerContext) -> None:
            global iface

            iface = iface
        """

    assert rules(source) == [("JOB001", "error")]


def test_annotations_and_defaults_are_not_body_reads() -> None:
    source = """
        from typing import TYPE_CHECKING

        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        if TYPE_CHECKING:
            from qgis.gui import QgsMapCanvas

        @job()
        def draw(ctx: WorkerContext, canvas: "QgsMapCanvas" = None) -> None:  # type: ignore[assignment]
            canvas = None
        """

    assert found(source) == []


def test_worker_safe_code_with_qgis_imports_is_not_reported() -> None:
    source = """
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext


        def read_features(path: str) -> int:
            from qgis.core import QgsVectorLayer

            layer = QgsVectorLayer(path, "in", "ogr")
            return layer.featureCount()


        @job()
        def count(ctx: WorkerContext, path: str) -> int:
            from qgis.core import QgsRectangle

            area = QgsRectangle(0, 0, 1, 1).area()
            ctx.progress.set(0.5)
            return read_features(path) + int(area)
        """

    assert found(source) == []


# -- JOB003: a by-name import, reported as a warning --------------------------------


def test_a_by_name_import_is_a_warning_about_what_cannot_be_read() -> None:
    source = """
        import importlib
        from qgis_sdk import job
        from qgis_sdk.core import WorkerContext

        @job()
        def load(ctx: WorkerContext, name: str) -> int:
            return len(importlib.import_module(name).__doc__)
        """

    assert rules(source) == [("JOB003", "warning")]
    assert found(source)[0].severity == "warning"


def test_the_sdk_alias_spelling_declares_jobs_too() -> None:
    source = """
        import qgis_sdk as sdk
        from qgis_sdk.core import WorkerContext

        @sdk.job()
        def load(ctx: WorkerContext) -> int:
            return len(ctx.project.layer_ids())
        """

    assert rules(source) == [("JOB002", "error")]


def test_the_plugin_instance_spelling_declares_jobs_too() -> None:
    source = """
        from qgis_sdk import QgisSdkPlugin
        from qgis_sdk.core import WorkerContext

        app = QgisSdkPlugin(id="demo", title="Demo")

        @app.job(id="demo.sum", title="Sum")
        def sum_of(ctx: WorkerContext) -> int:
            return len(ctx.layers.layer_ids())
        """

    assert rules(source) == [("JOB002", "error")]


# -- end to end (AC3) ---------------------------------------------------------------


def project(tmp_path: Path, plugin_source: str) -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text(textwrap.dedent(plugin_source), encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    return root


UNSAFE_PLUGIN = """
    from qgis.utils import iface
    from qgis_sdk import QgisSdkPlugin, job
    from qgis_sdk.core import WorkerContext

    app = QgisSdkPlugin(id="field_tools", title="Field Tools")


    @job(id="field_tools.reload", title="Reload")
    def reload_layers(ctx: WorkerContext) -> int:
        iface.mapCanvas().refresh()
        return len(ctx.project.layer_ids())
    """


def test_check_project_reports_the_unsafe_job_and_fails(tmp_path: Path) -> None:
    report = check_project(project(tmp_path, UNSAFE_PLUGIN))

    assert not report.ok
    # QGIS001 comes from the module-level `qgis.utils` import, which runs when
    # the plugin is loaded; the two job rules follow it.
    assert [d.rule for d in report.diagnostics] == ["QGIS001", "JOB001", "JOB002"]
    assert {d.path.as_posix() for d in report.diagnostics} == {"field_tools/plugin.py"}
    assert [d.line for d in report.diagnostics] == [2, 11, 12]


def test_the_check_command_fails_on_an_unsafe_job(tmp_path: Path) -> None:
    target = tmp_path / "survey_helper"
    write_scaffold(ScaffoldOptions.resolve(plugin="survey_helper"), target)
    plugin = target / "survey_helper" / "plugin.py"
    plugin.write_text(
        plugin.read_text(encoding="utf-8")
        + textwrap.dedent(
            """
            from qgis_sdk import job
            from qgis_sdk.core import WorkerContext


            @job(id="survey_helper.refresh", title="Refresh")
            def refresh(ctx: WorkerContext) -> int:
                return len(ctx.layers.layer_ids())
            """
        ),
        encoding="utf-8",
    )
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["check", "survey_helper"], obj=runtime)

    assert result.exit_code == 1
    assert any(": JOB002 " in line for line in runtime.stdout.splitlines())
    assert runtime.stdout.splitlines()[-1].endswith("1 problem")
