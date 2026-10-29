"""Narrow headless QGIS application test; not real Desktop qualification."""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = pytest.mark.qgis


def test_surface_only_plugin_gets_services_and_navigates_on_qgis(
    qgis_app, tmp_path, monkeypatch
):
    from qgis_sdk.adapters.desktop import host
    from qgis_sdk.models import QgisSdkScopeClosedError
    from test_surfaces_native import FakeIface

    package = tmp_path / "surface_only_native"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(
        """from qgis_sdk import QgisSdkPlugin, menu
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
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    iface = FakeIface()
    desktop = host("surface_only_native.plugin:app")(iface)
    try:
        desktop.initGui()
        assert desktop.runtime.actions == {}
        iface.menus["Plugins/Surface only"][0].trigger()
        (main,) = desktop.surfaces.dialogs
        ctx = main.surface.ctx
        assert ctx.desktop.iface is iface
        assert ctx.algorithms is desktop.context.algorithms
        assert ctx.styles is desktop.context.styles
        assert ctx.algorithms.describe("native:buffer").id == "native:buffer"
        main.surface.show.click()
        assert len(desktop.surfaces.dialogs) == 2
        detail = desktop.surfaces.dialogs[1]
        assert detail.surface.initial["origin"] == "main"
        main.widget.close()
        qgis_app.processEvents()
        assert main.scope.closed
        assert not detail.scope.closed and not desktop.context.scope.closed
        for name in ("algorithms", "styles", "desktop", "ui"):
            with pytest.raises(QgisSdkScopeClosedError):
                getattr(ctx, name)
        assert (
            detail.surface.ctx.algorithms.describe("native:buffer").id
            == "native:buffer"
        )
    finally:
        desktop.unload()
        iface.window.close()
        qgis_app.processEvents()
        for name in list(sys.modules):
            if name == "surface_only_native" or name.startswith("surface_only_native."):
                del sys.modules[name]


def test_lowered_apps_run_on_real_qgis_host_and_clean_up(
    qgis_app, tmp_path, monkeypatch
):
    from qgis.core import QgsApplication
    from qgis_sdk.adapters.desktop import host
    from qgis_sdk.declarations import QgisSdkDeclarationError
    from test_surfaces_native import FakeIface

    package = tmp_path / "application_native"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    template = """
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
    for name, key in (("one", "1"), ("two", "2")):
        (package / f"{name}.py").write_text(
            template.format(name=name, key=key), encoding="utf-8"
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    first_module = importlib.import_module("application_native.one")
    second_module = importlib.import_module("application_native.two")
    iface = FakeIface()
    one = host("application_native.one:app")(iface)
    two = host("application_native.two:app")(iface)
    registry = QgsApplication.processingRegistry()
    try:
        one.initGui()
        two.initGui()
        assert registry.providerById("application_one") is not None
        assert registry.providerById("application_two") is not None
        assert len(iface.toolbar) == 2
        assert len(iface.shortcuts) == 2
        collision = host("application_native.one:app")(iface)
        with pytest.raises(QgisSdkDeclarationError, match="application_one"):
            collision.initGui()
        assert collision.context.scope.closed
        assert registry.providerById("application_one") is not None
        assert len(iface.toolbar) == 2
        iface.toolbar[0].trigger()
        iface.toolbar[1].trigger()
        assert first_module.calls == [True] and second_module.calls == [True]
        assert len(one.surfaces.dialogs) == len(two.surfaces.dialogs) == 1
        one.unload()
        assert one.context.scope.closed
        assert first_module.closed == [True]
        assert registry.providerById("application_one") is None
        assert registry.providerById("application_two") is not None
        assert len(iface.toolbar) == len(iface.shortcuts) == 1
        iface.toolbar[0].trigger()
        assert second_module.calls == [True, True]
        restarted = host("application_native.one:app")(iface)
        try:
            restarted.initGui()
            assert registry.providerById("application_one") is not None
            iface.toolbar[-1].trigger()
            assert first_module.calls == [True, True]
        finally:
            restarted.unload()
        assert first_module.closed == [True, True]
        assert registry.providerById("application_two") is not None
    finally:
        one.unload()
        two.unload()
        iface.window.close()
        qgis_app.processEvents()
        for name in list(sys.modules):
            if name == "application_native" or name.startswith("application_native."):
                del sys.modules[name]
    assert second_module.closed == [True, True]
    assert registry.providerById("application_two") is None
    assert iface.toolbar == [] and iface.shortcuts == [] and iface.menus == {}
