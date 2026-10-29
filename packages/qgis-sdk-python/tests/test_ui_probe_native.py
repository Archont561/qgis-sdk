"""The UI probe against a real plugin: open, act through QTest, re-capture.

Runs the probe in this process under a headless ``QgsApplication``. The plugin
is a real scaffold-shaped package written to ``tmp_path`` and started through
its generated ``classFactory``, so the surfaces reached are the ones a host
opened - not widgets a test built by hand.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.qgis

pytest.importorskip("qgis.core")

from qgis_sdk_tools.devtools.ui_probe import (
    ActStep,
    CaptureRequest,
    perform,
    run,
)

PLUGIN_SOURCE = '''
"""A declared form whose Run button calls the plugin's action."""

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext
from qgis_sdk.ui import Column, Dialog, Form, Number, RunButton

app = QgisSdkPlugin(id="probe_demo", title="Probe demo")

CALLS = []


@app.action(id="buffer", title="Buffer")
def buffer(ctx: PluginContext, distance: float) -> str:
    CALLS.append(distance)
    return f"buffered {distance}"


@app.surface
class BufferDialog(Dialog):
    title = "Buffer"

    def build(self):
        distance = Number("distance")
        form = Form([distance], action_id="buffer")
        return Column(
            "root",
            [distance, RunButton("run", "buffer", values=form)],
        )
'''

WIDGET_SOURCE = '''
"""The generated entry point, as ``qgis-sdk build`` writes it."""

from qgis_sdk.adapters.desktop import host

classFactory = host("probe_demo.plugin:app")
'''


@pytest.fixture
def project(qgis_app: Any, tmp_path):
    package = tmp_path / "probe_demo"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(textwrap.dedent(PLUGIN_SOURCE), encoding="utf-8")
    (package / "host.py").write_text(textwrap.dedent(WIDGET_SOURCE), encoding="utf-8")
    return tmp_path


def _request(project, tmp_path, **overrides):
    payload = {
        "project": str(project),
        "plugin": "probe_demo",
        "surface": "buffer_dialog",
        "out": str(tmp_path / "captures"),
        "screenshot": False,
    }
    payload.update(overrides)
    return CaptureRequest.from_mapping(payload)


def test_the_probe_lists_the_surfaces_a_plugin_declares(project, tmp_path):
    report = run(_request(project, tmp_path, surface="-"))
    assert report.ok, report.error
    assert report.surfaces == [
        {"id": "buffer_dialog", "kind": "dialog", "title": "Buffer"}
    ]
    assert report.files == {}, "listing writes no capture"


def test_open_reports_the_window_and_writes_nothing(project, tmp_path):
    """``dev.ui.open``: did the surface build, and what is on screen."""
    report = run(_request(project, tmp_path, open_only=True))
    assert report.ok, report.error
    assert report.files == {}, "opening is not capturing"
    opened = report.opened
    assert opened["surface"] == "buffer_dialog"
    assert opened["kind"] == "dialog"
    assert opened["title"] == "Buffer"
    assert opened["widget"].startswith("Q")
    assert opened["nodes"] >= 3, "the column and the widgets it holds were counted"
    assert opened["findings"] == []


def test_a_snapshot_is_written_without_driving_the_surface(project, tmp_path):
    report = run(_request(project, tmp_path))
    assert report.ok, report.error
    assert report.surface == "buffer_dialog"
    assert set(report.files) == {"json"}
    tree = _capture_json(report)
    assert tree["surface"] == "buffer_dialog"
    assert _value(tree, "form/distance") == 0.0


def test_act_fills_the_form_and_the_action_runs_with_the_typed_values(
    project, tmp_path
):
    """AC 2: synthetic input, the real action, and a re-capture that shows it."""
    report = run(
        _request(
            project,
            tmp_path,
            steps=[
                {"node": "form/distance", "verb": "set", "value": 5},
                {"node": "buttons/run", "verb": "click"},
            ],
        )
    )
    assert report.ok, report.error
    assert [step["verb"] for step in report.steps] == ["set", "click"]
    assert report.steps[0]["value"] == 5.0, "typing must reach the spin box"

    plugin = __import__("probe_demo.plugin", fromlist=["CALLS"])
    assert plugin.CALLS == [5.0], "the action ran with the typed value"

    tree = _capture_json(report)
    assert _value(tree, "form/distance") == 5.0, "the re-capture shows the new state"


def test_a_node_that_is_not_there_fails_by_name(project, tmp_path):
    report = run(
        _request(
            project,
            tmp_path,
            steps=[{"node": "form/absent", "verb": "set", "value": 1}],
        )
    )
    assert report.ok is False
    assert "form/absent" in (report.error or "")


def test_an_unknown_surface_names_what_is_declared(project, tmp_path):
    report = run(_request(project, tmp_path, surface="absent"))
    assert report.ok is False
    assert "declares no surface named 'absent'" in (report.error or "")
    assert "buffer_dialog" in (report.error or "")


def test_an_unknown_verb_is_refused_before_anything_starts():
    with pytest.raises(ValueError, match="unknown verb"):
        ActStep.from_mapping({"node": "form/distance", "verb": "wiggle"})


def test_perform_reports_the_value_it_left_behind(qgis_app):
    from qgis.PyQt.QtWidgets import QLineEdit

    field = QLineEdit()
    field.show()
    try:
        assert perform(field, ActStep("form/name", "set", "Ada"))["value"] == "Ada"
        assert perform(field, ActStep("form/name", "type", "!"))["value"] == "Ada!"
        assert perform(field, ActStep("form/name", "focus", None)) == {"value": "Ada!"}
        assert field.hasFocus()
    finally:
        field.deleteLater()


def _capture_json(report):
    """The capture the probe left on disk, read back as the tree it stores."""
    return json.loads(Path(report.files["json"]).read_text(encoding="utf-8"))


def _value(tree, node_id):
    """The per-role value of one node, wherever it sits in the tree."""

    def walk(nodes):
        for node in nodes:
            if node["id"] == node_id:
                return node["value"]
            found = walk(node.get("children", ()))
            if found is not None:
                return found
        return None

    return walk(tree["nodes"])
