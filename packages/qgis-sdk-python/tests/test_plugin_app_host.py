"""Application discovery through the supported Desktop host boundary."""

from pathlib import Path

import pytest
from qgis_sdk import QgisSdkDeclarationError, QgisSdkPlugin
from qgis_sdk.adapters.desktop import (
    DesktopLifecycleAdapter,
    create_class_factory,
    host,
)
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.testing import RecordingNotifications


def test_direct_desktop_adapters_accept_applications_and_reject_classes() -> None:
    app = QgisSdkPlugin(id="example", title="Example")

    @app.action(id="double", title="Double")
    def double(ctx: PluginContext, value: int) -> int:
        return value * 2

    def context_factory(iface: object) -> PluginContext:
        scope = ResourceScope()
        return PluginContext(scope=scope, notifications=RecordingNotifications(scope))

    for factory in (
        lambda: DesktopLifecycleAdapter(app, None, context_factory=context_factory),
        lambda: create_class_factory(app, context_factory=context_factory)(None),
    ):
        adapter = factory()
        adapter.initGui()
        try:
            assert adapter.runtime.actions["double"](21) == 42
        finally:
            adapter.unload()

    from qgis_sdk.declarations._plugin import plugin

    @plugin(id="legacy", title="Legacy")
    class Legacy:
        pass

    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        DesktopLifecycleAdapter(Legacy, None, context_factory=context_factory)
    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        create_class_factory(Legacy, context_factory=context_factory)


from qgis_sdk_tools.generate import describe_plugin_spec


def test_host_resolves_module_app_and_dispatches_action(
    tmp_path: Path, monkeypatch
) -> None:
    package = tmp_path / "app_host_example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(
        "from qgis_sdk import QgisSdkPlugin\n"
        "from qgis_sdk.core import PluginContext\n"
        "app = QgisSdkPlugin(id='example', title='Example')\n"
        "@app.action(id='double', title='Double')\n"
        "def double(ctx: PluginContext, value: int) -> int:\n"
        "    return value * 2\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    description = describe_plugin_spec("app_host_example.plugin:app")
    assert [action["id"] for action in description["actions"]] == ["double"]
    factory = host("app_host_example.plugin:app")
    desktop = factory(None)
    desktop.initGui()
    try:
        assert desktop.runtime.actions["double"](value=21) == 42
    finally:
        desktop.unload()
