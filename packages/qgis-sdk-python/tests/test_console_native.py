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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_a_handle_dr_p1(_s):
    assert _s.session.plugins() == (PACKAGE,)
    _s.handle = _s.session.plugin(PACKAGE)

    assert _s.handle.name == PACKAGE
    assert _s.handle.description.id == "console_tools"
    assert _s.handle.actions == ("buffer", "count")
    assert _s.handle.surfaces() == ("buffer_dialog",)
    assert _s.handle.algorithms == (f"{PACKAGE}:centroid",)
    assert _s.handle.state.value == "running"
    assert _s.handle.ctx is _s.loaded.context

    assert _s.handle.run("count") == 0


def _cc_test_a_handle_dr_p2(_s):
    assert _s.handle.run("buffer", distance=10.0) == "roads+10"
    assert _s.handle.run("buffer", distance=1.5, layer_id="rivers") == "rivers+1.5"

    with pytest.raises(_s.QgisSdkBridgeError) as _s.refused:
        _s.handle.run("buffer", distance="far")
    assert "payload.distance" in str(_s.refused.value)

    _s.opened = _s.handle.open("buffer")
    _s.dialog = _s.loaded.surfaces.dialogs[0]
    assert _s.opened is _s.dialog.surface
    assert _s.dialog.widget.windowTitle() == "Buffer a layer"
    _s.label = _s.dialog.widget.findChild(_s.QtWidgets.QLabel)


def _cc_test_a_handle_dr_p3(_s):
    assert _s.label is not None and _s.label.text() == "distance"

    # The class name and the surface id reach the same surface.
    assert _s.handle.open("BufferDialog") is not _s.opened
    assert len(_s.loaded.surfaces.dialogs) == 2


def _cc_test_a_handle_dr_p4(_s):
    from qgis.PyQt import QtWidgets

    _s.QtWidgets = QtWidgets
    from qgis_sdk.console import connect

    _s.connect = connect
    from qgis_sdk.models import QgisSdkBridgeError

    _s.QgisSdkBridgeError = QgisSdkBridgeError

    with _s.connect() as _s.session:
        for _p in (
            _cc_test_a_handle_dr_p1,
            _cc_test_a_handle_dr_p2,
            _cc_test_a_handle_dr_p3,
        ):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r


_CC_TEXT_1 = """
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


pytestmark = pytest.mark.qgis

PACKAGE = "console_tools"
SPEC = f"{PACKAGE}.plugin:app"

PLUGIN = _CC_TEXT_1


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
    _s = _CcState(loaded=loaded, qgis_app=qgis_app)
    for _p in (_cc_test_a_handle_dr_p4,):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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
