"""The catalogue contract against the mounted QGIS widgets (TASK-96 AC 2).

Skips unless the QGIS bindings are importable. Every contract test of
:mod:`ui_catalogue_contract` runs here with ``mount()`` called after
``attach()``; the tests below cover the widget classes behind the
containers and the widget form of a surface opened by the host.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_a_widget_su_p1(_s):
    from qgis_sdk.adapters.qgis import NativeContextOptions, native_plugin_context

    _s.NativeContextOptions = NativeContextOptions
    _s.native_plugin_context = native_plugin_context
    from qgis_sdk.adapters.surfaces import SurfaceHost

    _s.SurfaceHost = SurfaceHost
    from qgis_sdk.bindings import _describe_lowered_bindings as describe_bindings

    _s.describe_bindings = describe_bindings
    from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope

    _s.PluginContext = PluginContext
    _s.PluginRuntime = PluginRuntime
    _s.ResourceScope = ResourceScope
    from qgis_sdk.declarations._plugin import plugin

    _s.plugin = plugin

    _s.seen: list[object] = []


def _cc_test_a_widget_su_p2(_s):

    class LegacyDialog(QWidget):
        kind = "dialog"
        title = "Legacy"

        def __init__(self, ctx: object) -> None:
            super().__init__()
            self.ctx = ctx
            _s.seen.append(ctx)
            QVBoxLayout(self).addWidget(QLabel("legacy", self))

        _s.__init__ = __init__

        def on_close(self) -> None:
            _s.seen.append("closed")

        _s.on_close = on_close

    _s.LegacyDialog = LegacyDialog


def _cc_test_a_widget_su_p3(_s):

    @_s.plugin(id="legacy_tools", title="Legacy tools")
    class LegacyTools:
        ctx: _s.PluginContext
        surfaces = (_s.LegacyDialog,)

    _s.LegacyTools = LegacyTools

    _s.scope = _s.ResourceScope()
    _s.context = _s.native_plugin_context(
        _s.scope, _s.NativeContextOptions(settings_prefix="legacy_tools")
    )


def _cc_test_a_widget_su_p4(_s):
    _s.host = _s.SurfaceHost(
        iface=None,
        plugin_id="legacy_tools",
        title="Legacy tools",
        bindings=_s.describe_bindings(_s.LegacyTools),
    )
    _s.runtime = _s.PluginRuntime._from_plugin_class(
        _s.LegacyTools, _s.context.with_services(ui=_s.host)
    )
    _s.host.attach(_s.runtime, _s.context)
    _s.runtime.start()
    _a_widget_surface_opens_phase1(_s.LegacyDialog, _s.host, _s.runtime, _s.seen)


def _a_widget_surface_opens_phase1(LegacyDialog, host, runtime, seen):
    try:
        opened = host.open(LegacyDialog)
        assert isinstance(opened, LegacyDialog)
        assert opened.ctx is seen[0]
        assert opened.ctx.has("log") is True
        assert dict(opened.initial) == {}
        assert host.dialogs[0].widget.windowTitle() == "Legacy"
        host.dialogs[0].widget.close()
        assert seen[-1] == "closed"
    finally:
        host.close_all()
        runtime.unload()


pytestmark = pytest.mark.qgis

try:
    from qgis.gui import QgsCollapsibleGroupBox
    from qgis.PyQt.QtWidgets import (
        QDialogButtonBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QScrollArea,
        QTableWidget,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native components need QGIS: {error}", allow_module_level=True)

from qgis_sdk.ui import (
    AcceptCancel,
    Column,
    Custom,
    Group,
    LogView,
    Panel,
    ResultTable,
    Row,
    Tabs,
    Text,
    ui_snapshot,
)
from ui_catalogue_contract import *
from ui_component_contract import Rendering, make_rendering


@pytest.fixture
def rendering(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Rendering]:
    """The native rendering: attached to the QGIS services and mounted."""
    yield from make_rendering(request, tmp_path, "native")


def test_the_containers_are_the_expected_qt_widgets(rendering: Rendering) -> None:
    row = rendering.attach(Row("row", [Text("a")]))
    column = rendering.attach(Column("column", [Text("b")]))
    panel = rendering.attach(Panel("panel", [Text("c")]))
    scrolling = rendering.attach(Panel("scrolling", [Text("d")], scrollable=True))
    group = rendering.attach(Group("group", [Text("e")], label="Options"))
    folding = rendering.attach(Group("folding", [Text("f")], collapsible=True))
    tabs = rendering.attach(Tabs("tabs", [Column("one", [Text("g")])]))

    assert isinstance(row.widget.layout(), QHBoxLayout)
    assert isinstance(column.widget.layout(), QVBoxLayout)
    assert isinstance(panel.widget.layout(), QVBoxLayout)
    assert isinstance(scrolling.widget, QScrollArea)
    assert scrolling.widget.widget().findChild(QWidget, "form/d") is not None
    assert type(group.widget) is QGroupBox
    assert group.widget.title() == "Options"
    assert isinstance(folding.widget, QgsCollapsibleGroupBox)
    assert isinstance(tabs.widget, QTabWidget)
    assert rendering.attach(LogView("log")).widget.__class__ is QPlainTextEdit
    assert isinstance(rendering.attach(ResultTable("t", ["a"])).widget, QTableWidget)
    assert isinstance(rendering.attach(AcceptCancel()).widget, QDialogButtonBox)


def test_custom_accepts_a_built_widget_and_reparents_it(rendering: Rendering) -> None:
    label = QLabel("ready")
    custom = Custom("ready", label)
    assert custom.factory is False
    root = rendering.attach(Column("root", [custom]))

    assert custom.widget is label
    assert label.parent() is root.widget
    assert label.objectName() == "custom/ready"
    assert ui_snapshot(root.widget)["children"][0]["text"] == "ready"


def test_a_widget_surface_opens_under_the_host(qgis_app: object) -> None:
    _s = _CcState(qgis_app=qgis_app)
    for _p in (
        _cc_test_a_widget_su_p1,
        _cc_test_a_widget_su_p2,
        _cc_test_a_widget_su_p3,
        _cc_test_a_widget_su_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
