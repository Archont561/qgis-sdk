"""``qgis-sdk ui``: one request into a QGIS process, one capture out (decision-51).

The command never touches a widget itself - it writes a request, runs the probe
in a QGIS interpreter and reads the report back - so these tests stand in for
QGIS with the fake runtime's recorded processes and answer with the report the
probe would have written.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.devtools.dev import STATE_DIRECTORY
from qgis_sdk_tools.devtools.ui_probe import (
    PROBE_ENTRYPOINT,
    REQUEST_ENV,
    CaptureRequest,
)
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from test_devtools_installs import make_prefix
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "probe_demo"
    write_scaffold(ScaffoldOptions.resolve("probe_demo"), root)
    return root


@pytest.fixture
def prefix(tmp_path: Path) -> Path:
    return make_prefix(tmp_path)


def _tree() -> dict[str, object]:
    return {
        "surface": "buffer_dialog",
        "kind": "dialog",
        "title": "Buffer",
        "size": [400, 300],
        "scale": 1.0,
        "nodes": [{"id": "form/distance", "role": "spinbox", "value": 5.0}],
        "findings": [],
    }


def _writes(report: dict[str, object], out: Path, stems: Sequence[str]) -> None:
    """Write the capture files the probe would have written."""
    for stem in stems:
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{stem}.json").write_text(json.dumps(_tree()), encoding="utf-8")


@pytest.fixture
def answering(project: Path, prefix: Path):
    """A fake runtime whose ``run_process`` answers as the probe would."""

    def build(
        *,
        payload: dict[str, object] | None = None,
        stems: Sequence[str] = ("buffer_dialog",),
        exit_code: int = 0,
        write_report: bool = True,
    ) -> tuple[FakeCliRuntime, list[CaptureRequest]]:
        requests: list[CaptureRequest] = []
        opened: dict[str, FakeCliRuntime] = {}

        def run_process(argv: Sequence[str], cwd: Path) -> int:
            # The fake records the environment it was given; the request file
            # the command pointed the probe at is the one to answer.
            env = opened["runtime"].environments[-1]
            assert env is not None
            request = json.loads(Path(env[REQUEST_ENV]).read_text(encoding="utf-8"))
            requests.append(CaptureRequest.from_mapping(request))
            if stems:
                _writes({}, Path(request["out"]), stems)
            if write_report:
                report = {
                    "ok": exit_code == 0,
                    "plugin": "probe_demo",
                    "surfaces": [
                        {"id": "buffer_dialog", "kind": "dialog", "title": "Buffer"}
                    ],
                    "surface": request["surface"],
                    "opened": {
                        "surface": "buffer_dialog",
                        "kind": "dialog",
                        "title": "Buffer",
                        "widget": "QDialog",
                        "size": [400, 300],
                        "nodes": 7,
                        "findings": [],
                    },
                    "steps": [
                        {
                            "node": "form/distance",
                            "verb": "set",
                            "value": 5,
                            "value_after": 5.0,
                        }
                    ],
                    "files": {
                        kind: str(Path(request["out"]) / f"{stem}.{kind}")
                        for stem in stems
                        for kind in ("json",)
                    },
                    "error": None if exit_code == 0 else "the action refused",
                }
                if payload:
                    report.update(payload)
                Path(request["report"]).write_text(json.dumps(report), encoding="utf-8")
            return exit_code

        runtime = FakeCliRuntime(project, {"PATH": "/nowhere"}, run_process=run_process)
        opened["runtime"] = runtime
        return runtime, requests

    return build


def test_snapshot_runs_the_probe_in_the_configured_qgis(answering, project, prefix):
    runtime, requests = answering()
    result = runner.invoke(
        app,
        ["ui", "snapshot", "buffer_dialog", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )
    assert result.exit_code == 0, runtime.stderr
    argv, cwd = runtime.processes[0]
    assert argv == (str(prefix.resolve() / "bin" / "python"), "-m", PROBE_ENTRYPOINT)
    assert cwd == project.resolve()
    env = runtime.environments[0]
    assert env is not None
    assert env["QGIS_PREFIX_PATH"] == str(prefix.resolve())
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert str(project.resolve()) in env["PYTHONPATH"].split(os.pathsep)
    request = requests[0]
    assert request.plugin == "probe_demo"
    assert request.surface == "buffer_dialog"
    assert request.out == project.resolve() / STATE_DIRECTORY / "ui"
    assert request.report == project.resolve() / STATE_DIRECTORY / "ui" / "report.json"
    assert "json:" in runtime.stdout
    assert str(request.out) in runtime.stdout


def test_the_request_is_left_in_the_workspace_for_the_next_run(
    answering, project, prefix
):
    runtime, _ = answering()
    result = runner.invoke(
        app,
        ["ui", "snapshot", "buffer_dialog", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )
    assert result.exit_code == 0, runtime.stderr
    written = project / STATE_DIRECTORY / "ui" / "request.json"
    assert json.loads(written.read_text(encoding="utf-8"))["surface"] == (
        "buffer_dialog"
    )


def test_list_asks_for_the_declared_surfaces_and_prints_them(
    answering, project, prefix
):
    runtime, requests = answering(stems=())
    result = runner.invoke(
        app, ["ui", "list", "--qgis-prefix", str(prefix)], obj=runtime
    )
    assert result.exit_code == 0, runtime.stderr
    assert requests[0].surface == "-"
    assert requests[0].screenshot is False
    assert json.loads(runtime.stdout) == [
        {"id": "buffer_dialog", "kind": "dialog", "title": "Buffer"}
    ]


def test_list_can_be_read_as_yaml(answering, project, prefix):
    runtime, _ = answering(stems=())
    result = runner.invoke(
        app,
        ["ui", "list", "--qgis-prefix", str(prefix), "--format", "yaml"],
        obj=runtime,
    )
    assert result.exit_code == 0, runtime.stderr
    assert "id: buffer_dialog" in runtime.stdout


def test_an_unknown_format_is_refused_before_anything_runs(answering, project):
    runtime, _ = answering()
    result = runner.invoke(
        app, ["ui", "snapshot", "buffer_dialog", "--format", "toml"], obj=runtime
    )
    assert result.exit_code != 0
    assert runtime.processes == []


def test_open_reports_the_window_without_writing_a_capture(answering, project, prefix):
    runtime, requests = answering(stems=())
    result = runner.invoke(
        app, ["ui", "open", "buffer_dialog", "--qgis-prefix", str(prefix)], obj=runtime
    )
    assert result.exit_code == 0, runtime.stderr
    assert requests[0].open_only is True
    assert json.loads(runtime.stdout)["widget"] == "QDialog"
    assert "nodes" in json.loads(runtime.stdout)


def test_snapshot_prints_the_capture_when_yaml_was_asked_for(
    answering, project, prefix
):
    runtime, _ = answering()
    result = runner.invoke(
        app,
        [
            "ui",
            "snapshot",
            "buffer_dialog",
            "--qgis-prefix",
            str(prefix),
            "--format",
            "yaml",
        ],
        obj=runtime,
    )
    assert result.exit_code == 0, runtime.stderr
    assert "surface: buffer_dialog" in runtime.stdout
    assert "json:" not in runtime.stdout


def test_act_sends_each_step_and_reports_the_value_it_left_behind(
    answering, project, prefix
):
    runtime, requests = answering(stems=("buffer_dialog-before", "buffer_dialog"))
    result = runner.invoke(
        app,
        [
            "ui",
            "act",
            "buffer_dialog",
            "--step",
            "form/distance:set:5",
            "--step",
            "buttons/run:click",
            "--qgis-prefix",
            str(prefix),
        ],
        obj=runtime,
    )
    assert result.exit_code == 0, runtime.stderr
    steps = requests[0].steps
    assert [(step.node, step.verb, step.value) for step in steps] == [
        ("form/distance", "set", "5"),
        ("buttons/run", "click", None),
    ]
    assert "form/distance set -> 5.0" in runtime.stdout


def test_act_without_a_step_says_what_it_needs_and_runs_nothing(answering, project):
    runtime, _ = answering()
    result = runner.invoke(app, ["ui", "act", "buffer_dialog"], obj=runtime)
    assert result.exit_code == 2
    assert "--step NODE:VERB[:VALUE]" in runtime.stderr
    assert runtime.processes == []


def test_an_unknown_verb_is_refused_with_the_verbs_that_exist(answering, project):
    runtime, _ = answering()
    result = runner.invoke(
        app,
        ["ui", "act", "buffer_dialog", "--step", "form/distance:wiggle"],
        obj=runtime,
    )
    assert result.exit_code == 2
    assert "click, focus, select, set, type" in result.stderr
    assert runtime.processes == []


def test_a_malformed_step_names_the_shape_it_wanted(answering, project):
    runtime, _ = answering()
    result = runner.invoke(
        app, ["ui", "act", "buffer_dialog", "--step", "nothing"], obj=runtime
    )
    assert result.exit_code == 2
    assert "NODE:VERB[:VALUE]" in result.stderr


def test_a_failing_probe_reports_the_traceback_and_exits_nonzero(
    answering, project, prefix
):
    runtime, _ = answering(exit_code=1, stems=())
    result = runner.invoke(
        app,
        ["ui", "snapshot", "buffer_dialog", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )
    assert result.exit_code == 1
    assert "the action refused" in runtime.stderr


def test_a_probe_that_wrote_no_report_is_reported_not_ignored(
    answering, project, prefix
):
    runtime, _ = answering(stems=(), write_report=False)
    result = runner.invoke(
        app,
        ["ui", "snapshot", "buffer_dialog", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )
    assert result.exit_code != 0
    assert "wrote no report" in runtime.stderr


def test_a_qgis_install_without_an_interpreter_explains_itself(tmp_path, project):
    prefix = make_prefix(tmp_path)
    (prefix / "bin" / "python").unlink()
    runtime = FakeCliRuntime(project, {"PATH": "/nowhere"})
    result = runner.invoke(
        app,
        ["ui", "snapshot", "buffer_dialog", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )
    assert result.exit_code == 2
    assert "no Python interpreter" in runtime.stderr
    assert runtime.processes == []


def test_diff_exits_one_only_when_the_structure_changed(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(_tree()), encoding="utf-8")
    after.write_text(json.dumps(_tree()), encoding="utf-8")
    runtime = FakeCliRuntime(tmp_path)

    same = runner.invoke(app, ["ui", "diff", str(before), str(after)], obj=runtime)
    assert same.exit_code == 0
    assert "no differences" in runtime.stdout

    moved = _tree()
    moved["nodes"] = [{"id": "form/distance", "role": "spinbox", "value": 7.0}]
    after.write_text(json.dumps(moved), encoding="utf-8")
    changed = runner.invoke(app, ["ui", "diff", str(before), str(after)], obj=runtime)
    assert changed.exit_code == 1
    assert "form/distance" in runtime.stdout


def test_diff_keeps_a_pixel_only_change_out_of_the_verdict(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    tree = _tree()
    tree["screenshot"] = "sha256:" + "a" * 64
    before.write_text(json.dumps(tree), encoding="utf-8")
    tree["screenshot"] = "sha256:" + "b" * 64
    after.write_text(json.dumps(tree), encoding="utf-8")
    runtime = FakeCliRuntime(tmp_path)

    result = runner.invoke(app, ["ui", "diff", str(before), str(after)], obj=runtime)

    assert result.exit_code == 0
    assert "the structure did not" in runtime.stdout


def test_diff_can_answer_as_json(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(_tree()), encoding="utf-8")
    moved = _tree()
    moved["title"] = "Buffered"
    after.write_text(json.dumps(moved), encoding="utf-8")
    runtime = FakeCliRuntime(tmp_path)

    result = runner.invoke(
        app, ["ui", "diff", str(before), str(after), "--json"], obj=runtime
    )

    assert result.exit_code == 1
    payload = json.loads(runtime.stdout)
    assert payload["structural"] is True
    assert payload["changes"][0]["field"] == "title"
