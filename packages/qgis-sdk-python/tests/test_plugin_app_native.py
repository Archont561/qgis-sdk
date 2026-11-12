"""Narrow headless QGIS application test; not real Desktop qualification."""

from __future__ import annotations

import importlib
import sys

import pytest


class _CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak1:
    """A loop break travelling out of a phase."""


class _CcContinue1:
    """A loop continue travelling out of a phase."""


def _cc_test_lowered_app_p1(_s1):
    from qgis.core import QgsApplication

    _s1.QgsApplication = QgsApplication
    from qgis_sdk.adapters.desktop import host

    _s1.host = host
    from qgis_sdk.declarations import QgisSdkDeclarationError

    _s1.QgisSdkDeclarationError = QgisSdkDeclarationError
    from test_surfaces_native import FakeIface

    _s1.FakeIface = FakeIface

    _s1.package = _s1.tmp_path / "application_native"
    _s1.package.mkdir()
    (_s1.package / "__init__.py").write_text("", encoding="utf-8")
    _s1.template = _CC_TEXT_2


def _cc_test_lowered_app_p2(_s1):
    _s1.one.initGui()
    _s1.two.initGui()
    assert _s1.registry.providerById("application_one") is not None
    assert _s1.registry.providerById("application_two") is not None
    assert len(_s1.iface.toolbar) == 2
    assert len(_s1.iface.shortcuts) == 2
    _s1.collision = _s1.host("application_native.one:app")(_s1.iface)
    with pytest.raises(_s1.QgisSdkDeclarationError, match="application_one"):
        _s1.collision.initGui()
    assert _s1.collision.context.scope.closed
    assert _s1.registry.providerById("application_one") is not None
    assert len(_s1.iface.toolbar) == 2


def _cc_test_lowered_app_p3(_s1):
    _s1.iface.toolbar[0].trigger()
    _s1.iface.toolbar[1].trigger()
    assert _s1.first_module.calls == [True] and _s1.second_module.calls == [True]
    assert len(_s1.one.surfaces.dialogs) == len(_s1.two.surfaces.dialogs) == 1
    _s1.one.unload()
    assert _s1.one.context.scope.closed
    assert _s1.first_module.closed == [True]
    assert _s1.registry.providerById("application_one") is None
    assert _s1.registry.providerById("application_two") is not None
    assert len(_s1.iface.toolbar) == len(_s1.iface.shortcuts) == 1
    _s1.iface.toolbar[0].trigger()
    assert _s1.second_module.calls == [True, True]


def _cc_test_lowered_app_p4(_s1):
    _s1.restarted = _s1.host("application_native.one:app")(_s1.iface)
    try:
        _s1.restarted.initGui()
        assert _s1.registry.providerById("application_one") is not None
        _s1.iface.toolbar[-1].trigger()
        assert _s1.first_module.calls == [True, True]
    finally:
        _s1.restarted.unload()
    assert _s1.first_module.closed == [True, True]
    assert _s1.registry.providerById("application_two") is not None


def _cc_test_lowered_app_p5(_s1):
    _s1.one.unload()
    _s1.two.unload()
    _s1.iface.window.close()
    _s1.qgis_app.processEvents()
    for name in list(sys.modules):
        _s1.name = name
        if _s1.name == "application_native" or _s1.name.startswith(
            "application_native."
        ):
            del sys.modules[_s1.name]


def _cc_test_lowered_app_p6(_s1):
    for name, key in (("one", "1"), ("two", "2")):
        _s1.name = name
        _s1.key = key
        (_s1.package / f"{_s1.name}.py").write_text(
            _s1.template.format(name=_s1.name, key=_s1.key), encoding="utf-8"
        )
    _s1.monkeypatch.syspath_prepend(str(_s1.tmp_path))
    _s1.first_module = importlib.import_module("application_native.one")
    _s1.second_module = importlib.import_module("application_native.two")
    _s1.iface = _s1.FakeIface()
    _s1.one = _s1.host("application_native.one:app")(_s1.iface)
    _s1.two = _s1.host("application_native.two:app")(_s1.iface)
    _s1.registry = _s1.QgsApplication.processingRegistry()


def _cc_test_lowered_app_p7(_s1):
    try:
        for _p1 in (
            _cc_test_lowered_app_p2,
            _cc_test_lowered_app_p3,
            _cc_test_lowered_app_p4,
        ):
            _r1 = _p1(_s1)
            if isinstance(_r1, _CcReturn1):
                return _r1
    finally:
        for _p1 in (_cc_test_lowered_app_p5,):
            _p1(_s1)
    assert _s1.second_module.closed == [True, True]
    assert _s1.registry.providerById("application_two") is None
    assert (
        _s1.iface.toolbar == [] and _s1.iface.shortcuts == [] and _s1.iface.menus == {}
    )


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_surface_onl_p1(_s):
    from qgis_sdk.adapters.desktop import host

    _s.host = host
    from qgis_sdk.models import QgisSdkScopeClosedError

    _s.QgisSdkScopeClosedError = QgisSdkScopeClosedError
    from test_surfaces_native import FakeIface

    _s.FakeIface = FakeIface

    _s.package = _s.tmp_path / "surface_only_native"
    _s.package.mkdir()
    (_s.package / "__init__.py").write_text("", encoding="utf-8")
    (_s.package / "plugin.py").write_text(
        _CC_TEXT_1,
        encoding="utf-8",
    )
    _s.monkeypatch.syspath_prepend(str(_s.tmp_path))


def _cc_test_surface_onl_p2(_s):
    _s.desktop.initGui()
    assert _s.desktop.runtime.actions == {}
    _s.iface.menus["Plugins/Surface only"][0].trigger()
    (_s.main,) = _s.desktop.surfaces.dialogs
    _s.ctx = _s.main.surface.ctx
    assert _s.ctx.desktop.iface is _s.iface
    assert _s.ctx.algorithms is _s.desktop.context.algorithms
    assert _s.ctx.styles is _s.desktop.context.styles
    assert _s.ctx.algorithms.describe("native:buffer").id == "native:buffer"
    _s.main.surface.show.click()
    assert len(_s.desktop.surfaces.dialogs) == 2
    _s.detail = _s.desktop.surfaces.dialogs[1]


def _cc_test_surface_onl_p3(_s):
    assert _s.detail.surface.initial["origin"] == "main"
    _s.main.widget.close()
    _s.qgis_app.processEvents()
    assert _s.main.scope.closed
    assert not _s.detail.scope.closed and not _s.desktop.context.scope.closed
    for name in ("algorithms", "styles", "desktop", "ui"):
        _s.name = name
        with pytest.raises(_s.QgisSdkScopeClosedError):
            getattr(_s.ctx, _s.name)
    assert (
        _s.detail.surface.ctx.algorithms.describe("native:buffer").id == "native:buffer"
    )


def _cc_test_surface_onl_p4(_s):
    _s.desktop.unload()
    _s.iface.window.close()
    _s.qgis_app.processEvents()
    for name in list(sys.modules):
        _s.name = name
        if _s.name == "surface_only_native" or _s.name.startswith(
            "surface_only_native."
        ):
            del sys.modules[_s.name]


def _cc_test_surface_onl_p5(_s):
    _s.iface = _s.FakeIface()
    _s.desktop = _s.host("surface_only_native.plugin:app")(_s.iface)
    try:
        for _p in (_cc_test_surface_onl_p2, _cc_test_surface_onl_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    finally:
        for _p in (_cc_test_surface_onl_p4,):
            _p(_s)


_CC_TEXT_1 = """from qgis_sdk import QgisSdkPlugin, menu
from qgis_sdk.ui import Button, Dialog, Text, on

app = QgisSdkPlugin(id="surface_only_native")

@app.surface
class Detail(Dialog):
    title = "Detail"
    origin = Text()
    close = Button(text="Close")

@app.surface
@menu("Plugins/Surface only")
class Main(Dialog):
    show = Button(text="Show")

    @on(show).clicked
    def show_detail(self):
        self.ctx.ui.open(Detail, initial={"origin": "main"})
"""
_CC_TEXT_2 = """
from qgis.PyQt.QtCore import QThread
from qgis.PyQt.QtWidgets import QApplication, QLabel
from qgis_sdk import QgisSdkPlugin, menu, shortcut, toolbar
from qgis_sdk.core import PluginContext
from qgis_sdk.providers import Provider
from qgis_sdk.ui import Dialog

calls = []
closed = []
child = QgisSdkPlugin(id="application.{name}.child")

@child.surface
class Report(Dialog):
    title = "Report"
    def build(self):
        return QLabel("report")
    def on_close(self):
        closed.append(True)

child.add_provider(Provider(id="application_{name}", title="{name}"))

@toolbar
@menu("Plugins/Application {name}")
@shortcut("Ctrl+Alt+{key}")
@child.action(id="show", title="Show")
def show(ctx: PluginContext) -> None:
    calls.append(QThread.currentThread() == QApplication.instance().thread())
    ctx.ui.open(Report)

app = QgisSdkPlugin(id="application.{name}", title="{name}")
app.include(child)

"""


pytestmark = pytest.mark.qgis


def test_surface_only_plugin_gets_services_and_navigates_on_qgis(
    qgis_app, tmp_path, monkeypatch
):
    _s = _CcState(qgis_app=qgis_app, tmp_path=tmp_path, monkeypatch=monkeypatch)
    for _p in (_cc_test_surface_onl_p1, _cc_test_surface_onl_p5):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def test_lowered_apps_run_on_real_qgis_host_and_clean_up(
    qgis_app, tmp_path, monkeypatch
):
    _s1 = _CcState1(qgis_app=qgis_app, tmp_path=tmp_path, monkeypatch=monkeypatch)
    for _p1 in (
        _cc_test_lowered_app_p1,
        _cc_test_lowered_app_p6,
        _cc_test_lowered_app_p7,
    ):
        _r1 = _p1(_s1)
        if isinstance(_r1, _CcReturn1):
            return _r1.value
    return None
