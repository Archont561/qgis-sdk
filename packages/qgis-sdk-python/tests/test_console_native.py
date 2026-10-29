"""``qgis_sdk.console`` over a real ``QgsApplication``, and a real plugin host.

``test_console_pure.py`` proves the resolution and refusal rules without QGIS.
This file is the other half (TASK-73 AC 1-2): ``connect()`` builds the same
context a Desktop plugin gets - ``ctx.layers`` is the real project, ``ctx.desktop``
is the live interface when there is one and a name when there is not - and a
handle over what ``classFactory`` returned runs the plugin's actions through the
bridge's validation, opens its surface through the plugin's own host, and lists
the Processing ids it registered.

The plugin is loaded the way QGIS loads it: ``classFactory(iface)``, ``initGui()``,
and the object put in ``qgis.utils.plugins`` under its package name - which is
all ``qgis.utils.loadPlugin`` does with it.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.qgis

PACKAGE = "console_tools"
SPEC = f"{PACKAGE}.plugin:app"

PLUGIN = """
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import AlgorithmContext, PluginContext
from qgis_sdk.models import LayerInput, VectorLayerInfo
from qgis_sdk.providers import Provider
from qgis_sdk.ui import Dialog

app = QgisSdkPlugin(id="console_tools", title="Console tools")


class BufferDialog(Dialog):
    title = "Buffer a layer"

    def build(self):
        from qgis.PyQt.QtWidgets import QLabel

        return QLabel("distance")


app.add_surface(BufferDialog)

provider = Provider(id=PACKAGE_ID, title="Console tools")


@provider.algorithm(id="centroid", title="Centroid")
def centroid(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
    from qgis_sdk.models import CentroidRequest

    return ctx.algorithms.execute(CentroidRequest(layer_id=layer_id))


app.add_provider(provider)


@app.action(id="count", title="Count")
def count(ctx: PluginContext) -> int:
    return len(ctx.project.layer_ids())


@app.action(id="buffer", title="Buffer")
def buffer_layer(ctx: PluginContext, distance: float, layer_id: str = "roads") -> str:
    return f"{layer_id}+{distance:g}"
"""


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The plugin package QGIS's ``classFactory`` will load."""
    root = tmp_path_factory.mktemp("console")
    package = root / PACKAGE
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(
        textwrap.dedent(PLUGIN).replace("PACKAGE_ID", f'"{PACKAGE}"'), encoding="utf-8"
    )
    sys.path.insert(0, str(root))
    try:
        yield root
    finally:
        sys.path.remove(str(root))
        for name in [m for m in sys.modules if m.split(".")[0] == PACKAGE]:
            del sys.modules[name]


@pytest.fixture
def loaded(qgis_app: Any, project: Path) -> Iterator[Any]:
    """The host QGIS holds for the plugin, registered in ``qgis.utils.plugins``."""
    import qgis.utils
    from qgis_sdk.adapters.desktop import host

    desktop = host(SPEC)(None)
    desktop.initGui()
    qgis.utils.plugins[PACKAGE] = desktop
    try:
        yield desktop
    finally:
        qgis.utils.plugins.pop(PACKAGE, None)
        desktop.unload()


def test_connect_without_an_iface_offers_every_service_but_desktop(
    qgis_app: Any,
) -> None:
    from qgis_sdk.console import connect
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    session = connect()
    try:
        assert session.ctx.has("desktop") is False
        with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
            _ = session.ctx.desktop
        assert refused.value.capability == "desktop"

        # The same curated services a plugin gets, over the real project.
        assert session.ctx.layers.list_layers() == ()
        assert session.ctx.project.layer_ids() == ()
        assert session.ctx.settings is not None
        session.ctx.notifications.info("from the console")
    finally:
        session.close()

    assert session.scope.closed is True
    session.close()  # idempotent


def test_connect_with_an_iface_exposes_the_desktop_service(qgis_app: Any) -> None:
    from qgis_sdk.console import connect

    class Iface:
        """Only what ``ctx.desktop`` is a wrapper around: nothing is called."""

    iface = Iface()
    with connect(iface=iface) as session:
        assert session.ctx.has("desktop") is True
        assert session.ctx.desktop.iface is iface


def test_a_handle_drives_the_plugin_qgis_holds(loaded: Any, qgis_app: Any) -> None:
    from qgis.PyQt import QtWidgets
    from qgis_sdk.console import connect
    from qgis_sdk.models import QgisSdkBridgeError

    with connect() as session:
        assert session.plugins() == (PACKAGE,)
        handle = session.plugin(PACKAGE)

        assert handle.name == PACKAGE
        assert handle.description.id == "console_tools"
        assert handle.actions == ("buffer", "count")
        assert handle.surfaces() == ("buffer_dialog",)
        assert handle.algorithms == (f"{PACKAGE}:centroid",)
        assert handle.state.value == "running"
        assert handle.ctx is loaded.context

        assert handle.run("count") == 0
        assert handle.run("buffer", distance=10.0) == "roads+10"
        assert handle.run("buffer", distance=1.5, layer_id="rivers") == "rivers+1.5"

        with pytest.raises(QgisSdkBridgeError) as refused:
            handle.run("buffer", distance="far")
        assert "payload.distance" in str(refused.value)

        opened = handle.open("buffer")
        dialog = loaded.surfaces.dialogs[0]
        assert opened is dialog.surface
        assert dialog.widget.windowTitle() == "Buffer a layer"
        label = dialog.widget.findChild(QtWidgets.QLabel)
        assert label is not None and label.text() == "distance"

        # The class name and the surface id reach the same surface.
        assert handle.open("BufferDialog") is not opened
        assert len(loaded.surfaces.dialogs) == 2


def test_a_session_the_plugin_hands_out_shares_its_services_and_closes_with_it(
    loaded: Any,
) -> None:
    session = loaded.console()

    assert session.ctx is loaded.context
    assert session.owns_scope is False
    assert session.plugin_name == "console_tools"

    session.close()

    assert loaded.runtime.state.value == "running"  # closing the view stops nothing
    assert session.closed is True


def test_the_plugins_own_unload_closes_its_sessions(loaded: Any, qgis_app: Any) -> None:
    from qgis_sdk.console import QgisSdkConsoleError

    session = loaded.console()

    loaded.unload()

    assert session.closed is True
    with pytest.raises(QgisSdkConsoleError, match="closed"):
        _ = session.ctx
