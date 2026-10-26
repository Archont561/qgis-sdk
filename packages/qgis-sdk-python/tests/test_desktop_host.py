"""``host(spec)``: the generated ``classFactory`` without QGIS or Qt (TASK-64).

The native half - a real ``QgsApplication``, providers in the registry, the
page in a dock - lives in ``test_desktop_host_native.py``. Here the bare
context: a starter test calls ``classFactory(None)`` and the plugin runs
with notifications and a scope, refusing ``ctx.desktop`` by name.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from qgis_sdk.adapters.desktop import (
    DesktopHost,
    MessageBarNotifications,
    QgisSdkHostError,
    host,
    resolve_plugin_spec,
)
from qgis_sdk.core import PluginContext, PluginRuntimeState
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

PACKAGE = "hosted_tools"


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("hosted")
    package = root / PACKAGE
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(
        textwrap.dedent(
            """
            from qgis_sdk import action, plugin
            from qgis_sdk.core import PluginContext, ResourceScope


            @plugin(id="hosted", title="Hosted tools")
            class HostedPlugin:
                ctx: PluginContext

                @action(id="ping", title="Ping")
                def ping(self, value: int) -> int:
                    return value

                @action(id="layers", title="Layers")
                def layers(self) -> list[str]:
                    return list(self.ctx.project.layer_ids())


            class Recording:
                def __init__(self):
                    self.messages = []

                def info(self, message):
                    self.messages.append(message)


            NOTIFICATIONS = Recording()


            def _own_context(iface):
                return PluginContext(notifications=NOTIFICATIONS, scope=ResourceScope())


            @plugin(id="hosted.custom", title="Custom context")
            class CustomContextPlugin:
                ctx: PluginContext
                context_factory = staticmethod(_own_context)

                @action(id="say", title="Say")
                def say(self, text: str) -> None:
                    self.ctx.notifications.info(text)


            not_a_class = 3
            """
        ),
        encoding="utf-8",
    )
    sys.path.insert(0, str(root))
    try:
        yield root
    finally:
        sys.path.remove(str(root))
        for name in [m for m in sys.modules if m.split(".")[0] == PACKAGE]:
            del sys.modules[name]


def test_host_returns_a_class_factory_that_runs_the_plugin_without_qgis(
    project: Path,
) -> None:
    class_factory = host(f"{PACKAGE}.plugin:HostedPlugin")

    assert class_factory.__name__ == "classFactory"
    held = class_factory(None)

    assert isinstance(held, DesktopHost)
    assert held.iface is None
    assert held.placement is None
    assert held.grants == ()
    assert held.view is None
    held.initGui()
    try:
        assert held.runtime.state is PluginRuntimeState.RUNNING
        assert held.runtime.actions["ping"](7) == 7
        assert not held.context.has("desktop")
        with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
            held.runtime.actions["layers"]()
        assert "project" in str(refused.value)
    finally:
        held.unload()
    assert held.runtime.state is PluginRuntimeState.STOPPED
    held.unload()  # repeat is safe


def test_the_bare_context_drops_messages_and_scopes_settings_by_plugin_id(
    project: Path,
) -> None:
    held = host(f"{PACKAGE}.plugin:HostedPlugin")(None)

    assert isinstance(held.context, PluginContext)
    assert isinstance(held.context.notifications, MessageBarNotifications)
    held.context.notifications.info("nobody listens")  # no iface: dropped
    assert held.context.scope.closed is False
    held.unload()
    assert held.context.scope.closed is True


def test_a_context_factory_class_attribute_replaces_the_default(
    project: Path,
) -> None:
    import importlib

    module = importlib.import_module(f"{PACKAGE}.plugin")
    held = host(f"{PACKAGE}.plugin:CustomContextPlugin")(None)
    held.initGui()
    try:
        held.runtime.actions["say"]("hello")
    finally:
        held.unload()

    assert module.NOTIFICATIONS.messages == ["hello"]
    assert held.context.notifications is module.NOTIFICATIONS


def test_show_view_without_a_declared_page_is_refused(project: Path) -> None:
    held = host(f"{PACKAGE}.plugin:HostedPlugin")(None)

    with pytest.raises(QgisSdkHostError, match="declares no page"):
        held.show_view()


def test_a_page_is_remembered_but_not_opened_until_asked(project: Path) -> None:
    class_factory = host(
        f"{PACKAGE}.plugin:HostedPlugin",
        placement="dock",
        grants=["layers.read", "project.layer_ids"],
    )
    held = class_factory(None)

    assert held.placement == "dock"
    # a grant selects its operations, an id selects one (decision-43)
    assert held.grants == ("layers.list", "layers.get", "project.layer_ids")
    assert held.view is None


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (f"{PACKAGE}.plugin", "pkg.module:Class"),
        (":HostedPlugin", "pkg.module:Class"),
        ("no_such_module_anywhere:Plugin", "cannot import"),
        (f"{PACKAGE}.plugin:Missing", "no attribute"),
        (f"{PACKAGE}.plugin:not_a_class", "not a class"),
    ],
)
def test_bad_specs_fail_by_name(project: Path, spec: str, message: str) -> None:
    with pytest.raises(QgisSdkHostError, match=message):
        resolve_plugin_spec(spec)


def test_an_undeclared_class_is_refused_before_any_class_factory_exists(
    project: Path,
) -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    with pytest.raises(QgisSdkDeclarationError):
        host(f"{PACKAGE}.plugin:Recording")


def test_unknown_placement_and_grants_are_refused_by_host(project: Path) -> None:
    with pytest.raises(QgisSdkHostError, match="placement must be one of"):
        host(f"{PACKAGE}.plugin:HostedPlugin", placement="window")
    with pytest.raises(QgisSdkHostError, match="unknown host grant 'layers.nope'"):
        host(f"{PACKAGE}.plugin:HostedPlugin", placement="dock", grants=["layers.nope"])
    with pytest.raises(QgisSdkHostError, match="grants need a page"):
        host(f"{PACKAGE}.plugin:HostedPlugin", grants=["layers.list"])


def test_the_plugin_module_is_imported_through_the_builtin_import_hook(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QGIS tracks a plugin's modules by wrapping ``builtins.__import__`` and
    drops exactly those on unload; a module that bypasses the hook survives
    a reload as a stale copy. ``host()`` must therefore import the plugin
    module the way ``from .plugin import ...`` would have (TASK-64)."""
    import builtins

    seen: list[str] = []
    real = builtins.__import__

    def tracking(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        module = real(name, globals, locals, fromlist, level)
        if level == 0:
            seen.append(module.__name__ if fromlist else name)
        return module

    for name in [m for m in sys.modules if m.split(".")[0] == PACKAGE]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(builtins, "__import__", tracking)

    resolve_plugin_spec(f"{PACKAGE}.plugin:HostedPlugin")

    assert f"{PACKAGE}.plugin" in seen
