"""Surface snapshots over real Qt: the tree, the PNG and the plugin's scope.

Runs under the offscreen QPA. Only the surfaces this host opened are visible;
a second plugin's window is never reachable from here (decision-51 point 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.PyQt.QtWidgets import QDialog, QWidget
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native snapshots need QGIS: {error}", allow_module_level=True)

from qgis_sdk.adapters.qgis import native_plugin_context
from qgis_sdk.adapters.snapshot import capture_surface
from qgis_sdk.adapters.surfaces import SurfaceHost
from qgis_sdk.bindings import _describe_lowered_bindings as describe_bindings
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.declarations._plugin import action, plugin
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui import Column, Dialog, Dock, Number, RunButton, canonical_json


class BufferDialog(Dialog):
    title = "Buffer"

    def build(self) -> Column:
        return Column(
            "root",
            [
                Number("distance"),
                RunButton("run", "buffer", values=lambda: {"distance": 2}),
            ],
        )


class Panel(Dock):
    title = "Panel"

    def build(self) -> Column:
        return Column("root", [Number("amount")])


@plugin(id="snapshot_host", title="Snapshot host")
class SnapshotPlugin:
    ctx: PluginContext
    surfaces = (BufferDialog, Panel)

    @action(id="buffer", title="Buffer")
    def buffer(self, distance: float) -> str:
        return f"buffered {distance}"


@pytest.fixture
def host(qgis_app: Any) -> Iterator[SurfaceHost]:
    scope = ResourceScope()
    context = native_plugin_context(scope, settings_prefix="snapshot_host")
    host = SurfaceHost(
        iface=None,
        plugin_id="snapshot_host",
        title="Snapshot host",
        bindings=describe_bindings(SnapshotPlugin),
    )
    runtime = PluginRuntime._from_plugin_class(
        SnapshotPlugin, context.with_services(ui=host)
    )
    host.attach(runtime, context)
    runtime.start()
    try:
        yield host
    finally:
        host.close_all()
        runtime.unload()


def test_a_dialog_capture_has_the_tree_the_png_and_the_roles(host: SurfaceHost):
    host.open(BufferDialog)
    (capture,) = host.snapshot()

    tree = capture.tree
    assert tree["surface"] == "buffer_dialog"
    assert tree["kind"] == "dialog"
    assert tree["title"] == "Buffer"
    assert tree["screenshot"].startswith("sha256:")
    assert capture.png is not None
    assert capture.png.startswith(b"\x89PNG\r\n\x1a\n")
    assert tree["findings"] == []

    nodes = {node["id"]: node for node in tree["nodes"]}
    (root,) = nodes["root"]["children"] if "root" not in nodes else (None,)
    del root  # the form sits under the dialog's own layout widget
    ids = _ids(tree["nodes"])
    assert "form/distance" in ids
    assert "buttons/run" in ids

    spin = _node(tree["nodes"], "form/distance")
    assert spin["role"] == "spinbox"
    assert spin["value"] == 0.0
    button = _node(tree["nodes"], "buttons/run")
    assert button["role"] == "button"
    assert button["value"] == "Run"
    assert button["declared"] == {"button": "run"}


def test_the_screenshot_digest_matches_the_captured_png(host: SurfaceHost):
    host.open(BufferDialog)
    (capture,) = host.snapshot()
    import hashlib

    assert capture.tree["screenshot"] == (
        "sha256:" + hashlib.sha256(capture.png or b"").hexdigest()
    )


def test_two_captures_of_an_unchanged_surface_are_byte_identical(host: SurfaceHost):
    host.open(BufferDialog)
    (first,) = host.snapshot()
    (second,) = host.snapshot(screenshot=False)
    # The PNG is still deterministic, so the digest is compared too.
    (third,) = host.snapshot()
    assert first.text == third.text
    assert canonical_json(second.tree) != first.text, "a missing screenshot shows"


def test_an_unknown_surface_id_is_refused(host: SurfaceHost):
    host.open(BufferDialog)
    with pytest.raises(QgisSdkUiError, match="no open surface named 'absent'"):
        host.snapshot("absent")


def test_only_open_surfaces_are_captured(host: SurfaceHost):
    host.open(BufferDialog)
    assert [capture.tree["surface"] for capture in host.snapshot()] == ["buffer_dialog"]

    host.open(Panel)
    assert sorted(capture.tree["surface"] for capture in host.snapshot()) == [
        "buffer_dialog",
        "panel",
    ]

    dock = host.docks[Panel]
    dock.widget.hide()
    assert [capture.tree["surface"] for capture in host.snapshot()] == ["buffer_dialog"]


def test_a_capture_writes_json_and_png(tmp_path):
    dialog = QDialog()
    dialog.setObjectName("standalone")
    dialog.resize(120, 40)
    capture = capture_surface(dialog, surface_id="standalone", kind="dialog")
    json_path, png_path = capture.write(tmp_path / "standalone")

    assert json_path.read_text(encoding="utf-8") == capture.text
    assert png_path is not None and png_path.read_bytes().startswith(b"\x89PNG")
    assert capture.tree["size"] == {"width": 120, "height": 40}
    dialog.deleteLater()


def _ids(nodes) -> set[str]:
    found: set[str] = set()

    def walk(node):
        found.add(node["id"])
        for child in node.get("children", ()):
            walk(child)

    for node in nodes:
        walk(node)
    return found


def _node(nodes, wanted: str) -> dict[str, Any]:
    for node in nodes:
        if node["id"] == wanted:
            return node
        for child in node.get("children", ()):
            try:
                return _node([child], wanted)
            except KeyError:
                continue
    raise KeyError(wanted)


def test_the_tree_contains_no_widget_from_outside_the_surface(host: SurfaceHost):
    outside = QWidget()
    outside.setObjectName("outside")
    host.open(BufferDialog)
    (capture,) = host.snapshot()
    assert "outside" not in _ids(capture.tree["nodes"])
    outside.deleteLater()
