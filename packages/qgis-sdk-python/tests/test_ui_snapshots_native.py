"""Approvals over real surfaces: two plugins loaded, only one of them captured.

The scope rule of decision-51 point 6 is what makes an approval safe to commit:
a capture holds the surfaces this plugin's host opened and nothing else. So the
second plugin's window is open, and visible, while every assertion here runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.PyQt.QtWidgets import QDialog, QWidget
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native snapshots need QGIS: {error}", allow_module_level=True)

from qgis_sdk.adapters.qgis import native_plugin_context
from qgis_sdk.adapters.surfaces import SurfaceHost
from qgis_sdk.bindings import _describe_lowered_bindings as describe_bindings
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.declarations._plugin import plugin
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui import Column, Dialog, Number
from qgis_sdk_tools.snapshots import SnapshotMismatch, Snapshots


class AlphaDialog(Dialog):
    title = "Alpha"

    def build(self) -> Column:
        return Column("root", [Number("alpha")])


class BetaDialog(Dialog):
    title = "Beta"

    def build(self) -> Column:
        return Column("root", [Number("beta")])


@plugin(id="alpha_host", title="Alpha host")
class AlphaPlugin:
    ctx: PluginContext
    surfaces = (AlphaDialog,)


@plugin(id="beta_host", title="Beta host")
class BetaPlugin:
    ctx: PluginContext
    surfaces = (BetaDialog,)


def _start(plugin_class: Any, plugin_id: str) -> SurfaceHost:
    """One plugin running on its own host, the way a scaffolded package does."""
    scope = ResourceScope()
    context = native_plugin_context(scope, settings_prefix=plugin_id)
    host = SurfaceHost(
        iface=None,
        plugin_id=plugin_id,
        title=plugin_id,
        bindings=describe_bindings(plugin_class),
    )
    runtime = PluginRuntime._from_plugin_class(
        plugin_class, context.with_services(ui=host)
    )
    host.attach(runtime, context)
    runtime.start()
    return host


@pytest.fixture
def two_plugins(qgis_app: Any) -> Iterator[tuple[SurfaceHost, SurfaceHost]]:
    """Two plugins loaded at once, each with its own host."""
    alpha = _start(AlphaPlugin, "alpha_host")
    beta = _start(BetaPlugin, "beta_host")
    try:
        yield alpha, beta
    finally:
        beta.close_all()
        alpha.close_all()


def test_a_capture_holds_only_the_plugin_that_made_it(
    two_plugins: tuple[SurfaceHost, SurfaceHost], tmp_path: Path
):
    alpha, beta = two_plugins
    alpha.open(AlphaDialog)
    beta.open(BetaDialog)
    result = Snapshots(tmp_path)(alpha.snapshot("alpha_dialog")[0])

    ids = _ids(result.capture.tree["nodes"])
    assert "form/alpha" in ids
    assert "form/beta" not in ids, "the other plugin's window is not this capture"
    assert result.capture.tree["surface"] == "alpha_dialog"


def test_a_host_refuses_the_id_the_other_plugin_owns(
    two_plugins: tuple[SurfaceHost, SurfaceHost],
):
    alpha, beta = two_plugins
    alpha.open(AlphaDialog)
    beta.open(BetaDialog)

    with pytest.raises(QgisSdkUiError, match="no open surface named 'beta_dialog'"):
        alpha.snapshot("beta_dialog")


def test_an_approved_surface_passes_and_a_moved_one_fails(
    two_plugins: tuple[SurfaceHost, SurfaceHost], tmp_path: Path
):
    alpha, _ = two_plugins
    alpha.open(AlphaDialog)
    Snapshots(tmp_path)(alpha.snapshot("alpha_dialog")[0]).approve()

    unchanged = Snapshots(tmp_path)
    assert unchanged(alpha.snapshot("alpha_dialog")[0]).matches is True
    unchanged.verify()

    _field(alpha.dialogs[0].widget, "form/alpha").setValue(7.0)
    moved = Snapshots(tmp_path)
    moved(alpha.snapshot("alpha_dialog")[0])
    with pytest.raises(SnapshotMismatch, match="form/alpha"):
        moved.verify()


def test_a_widget_the_test_built_is_captured_by_name(
    two_plugins: tuple[SurfaceHost, SurfaceHost], tmp_path: Path
):
    dialog = QDialog()
    dialog.setObjectName("standalone")
    dialog.resize(120, 40)
    try:
        result = Snapshots(tmp_path)(dialog, name="standalone")
        result.approve()
        assert result.capture.tree["size"] == {"width": 120, "height": 40}
        assert result.json_path.is_file()
        assert result.png_path is not None and result.png_path.is_file()
        assert result.png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        dialog.deleteLater()


def _field(widget: Any, name: str) -> Any:
    found = widget.findChild(QWidget, name)
    assert found is not None, f"{name} is not in the surface"
    return found


def _ids(nodes: Any) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        found.add(node["id"])
        for child in node.get("children", ()):
            walk(child)

    for node in nodes:
        walk(node)
    return found
