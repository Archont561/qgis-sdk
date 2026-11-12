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


def _cc_test_direct_desk_p1(_s):
    _s.app = QgisSdkPlugin(id="example", title="Example")

    @_s.app.action(id="double", title="Double")
    def double(ctx: PluginContext, value: int) -> int:
        return value * 2

    _s.double = double

    def context_factory(iface: object) -> PluginContext:
        scope = ResourceScope()
        return PluginContext(RecordingNotifications(scope), scope)

    _s.context_factory = context_factory


def _cc_test_direct_desk_p2(_s):

    for factory in (
        lambda: DesktopLifecycleAdapter(
            _s.app, None, context_factory=_s.context_factory
        ),
        lambda: create_class_factory(_s.app, context_factory=_s.context_factory)(None),
    ):
        _s.factory = factory
        _s.adapter = _s.factory()
        _s.adapter.initGui()
        try:
            assert _s.adapter.runtime.actions["double"](21) == 42
        finally:
            _s.adapter.unload()
    from qgis_sdk.declarations._plugin import plugin

    _s.plugin = plugin


def _cc_test_direct_desk_p3(_s):

    @_s.plugin(id="legacy", title="Legacy")
    class Legacy:
        pass

    _s.Legacy = Legacy

    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        DesktopLifecycleAdapter(_s.Legacy, None, context_factory=_s.context_factory)
    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        create_class_factory(_s.Legacy, context_factory=_s.context_factory)


def test_direct_desktop_adapters_accept_applications_and_reject_classes() -> None:
    _s = _CcState()
    for _p in (
        _cc_test_direct_desk_p1,
        _cc_test_direct_desk_p2,
        _cc_test_direct_desk_p3,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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
