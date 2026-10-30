"""TASK-80 AC 3: one plugin class, unchanged, serving both hosts.

The clause this file closes is the one AC 3 deferred: "the same plugin class
with ``hosts = [desktop, server]`` runs on both". It needs no QGIS on either
side - the Desktop host runs the real lifecycle without one
(``qgis_sdk.adapters.desktop.host``), and the server host is the same dispatcher
``qgis-sdk test --target server`` drives in CI - so the claim is checkable on a
machine that has neither QGIS nor a display.

What is asserted is what "runs on both" has to mean:

* each host sees only its own declarations: the action is an action on Desktop
  and is not a server hook, and the three hooks are served on the server and
  are not actions;
* each hook reports the host it actually ran on, ``desktop`` and ``server``,
  from the same class;
* a project declaring both hosts passes ``check``, while each host's
  declarations alone in a single-host project are HOST001/HOST002 (the rules
  themselves are pinned in ``test_check_hosts``);
* the server side refuses the Desktop capabilities by name instead of
  pretending to have them.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest
from qgis_sdk.adapters.desktop import host
from qgis_sdk.core import Host
from qgis_sdk.declarations import describe
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerRequest,
    ServerResponse,
    filter,
)
from qgis_sdk.testing import FakeServerInterface
from qgis_sdk_tools.check import check_project

DUAL = '''"""One plugin declaration for two hosts: an action and three server hooks."""

from __future__ import annotations

from qgis_sdk import QgisSdkPlugin, toolbar
from qgis_sdk.core import PluginContext
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)

app = QgisSdkPlugin(id="dual", title="Dual tools")


@toolbar(text="Dual tools")
@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> str:
    """The Desktop surface: it says which host ran it."""
    return f"{ctx.host.value}:{value}"


@filter()
def version(
    ctx: ServerContext, request: ServerRequest, response: ServerResponse
) -> ServerRequest | None:
    if request.param("VERSION") is None:
        return request.with_params(VERSION="1.3.0")
    return None


@service(name="DUAL", version="1.0.0")
def answer(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
    return ServerResponse.text(f"{ctx.host.value}:{request.param('VERSION')}")


@access_control()
def everything_public(ctx: ServerContext, request: ServerRequest, layer: str) -> bool:
    return True


# What a generated plugin's entry module exports for QGIS Server, in one line.
HOOKS = ServerHooks((version, answer, everything_public))
'''

PYPROJECT = """[project]
name = "dual-tools"
version = "0.1.0"
description = "Dual tools."
authors = [{ name = "Jane", email = "jane@example.org" }]
dependencies = ["qgis-sdk-runtime>=0.1,<99"]

[tool.qgis-sdk]
plugin = "dual.plugin:app"
qgis-minimum-version = "3.40"
hosts = ["desktop", "server"]
"""


@pytest.fixture
def dual(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The one plugin package on the import path, exactly as a project ships it."""
    root = tmp_path / "dual-tools"
    package = root / "dual"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(DUAL, encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    monkeypatch.syspath_prepend(str(root))
    return importlib.import_module("dual.plugin")


def request(**params: str) -> ServerRequest:
    return ServerRequest(
        method="GET", url="http://localhost/qgis/qgis_mapserv.fcgi", params=params
    )


def test_the_desktop_host_runs_the_same_module(dual: ModuleType) -> None:
    class_factory = host("dual.plugin:app")
    plugin = class_factory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.state.value == "running"
        # The action reads ctx.host, so this is the host that ran it.
        assert plugin.runtime.actions["ping"](7) == "desktop:7"
    finally:
        plugin.unload()
    assert plugin.runtime.state.value == "stopped"


def test_the_server_host_serves_the_same_module(dual: ModuleType) -> None:
    answered = FakeServerInterface().serve(dual.HOOKS, request(SERVICE="DUAL"))

    assert answered.status == 200
    # The service reads ctx.host too: the same class, the other host.
    assert answered.body == b"server:1.3.0"


def test_each_host_sees_only_its_own_declarations(dual: ModuleType) -> None:
    description = describe(dual.app)

    assert [action.id for action in description.actions] == ["ping"]
    # The three hooks are not actions, and the action is not a hook.
    assert len(dual.HOOKS) == 3
    assert [hook.__name__ for hook in dual.HOOKS] == [
        "version",
        "answer",
        "everything_public",
    ]
    assert "ping" not in [hook.__name__ for hook in dual.HOOKS]


def test_the_server_registers_nothing_the_desktop_declared(dual: ModuleType) -> None:
    interface = FakeServerInterface()
    interface.serve(dual.HOOKS, request(SERVICE="DUAL"))

    # One chain filter, one service for SERVICE=DUAL, one access-control hook:
    # the Desktop action is nowhere in what QGIS Server is given.
    assert [item.hook.__name__ for item in interface.filters] == ["version"]
    assert [name for name, _version, _handler in interface.services] == ["DUAL"]
    assert [item.hook.__name__ for item in interface.access_control] == [
        "everything_public"
    ]


def test_the_server_context_refuses_the_desktop_capabilities_by_name(
    dual: ModuleType,
) -> None:
    """The same class on the server has no ``ui`` and no ``desktop`` - by name."""
    seen: list[frozenset[str]] = []

    @filter()
    def inspect(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        seen.append(ctx.capabilities)
        # A view, the Desktop interface and the workers do not exist here, and
        # a capability the host never had is refused by name rather than faked.
        for name in ("jobs", "project"):
            with pytest.raises(QgisSdkUnsupportedCapabilityError, match=name):
                getattr(ctx, name)
        assert not hasattr(ctx, "desktop")
        assert not hasattr(ctx, "ui")
        assert ctx.host is Host.SERVER

    hooks = ServerHooks((inspect, *dual.HOOKS))
    answered = FakeServerInterface().serve(hooks, request(SERVICE="DUAL"))

    assert answered.status == 200
    assert seen == [frozenset()]
    assert Host.DESKTOP.value == "desktop"


def test_a_project_declaring_both_hosts_passes_the_check(
    dual: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "dual-tools"

    codes = {item.rule for item in check_project(root).diagnostics}
    assert "HOST001" not in codes
    assert "HOST002" not in codes

    # The contrast: the same module declaring only the Desktop host is HOST002,
    # and only the server is HOST001 - which is what makes the clean run mean
    # something.
    (root / "pyproject.toml").write_text(
        PYPROJECT.replace('hosts = ["desktop", "server"]', 'hosts = ["desktop"]'),
        encoding="utf-8",
    )
    assert "HOST002" in {item.rule for item in check_project(root).diagnostics}
    (root / "pyproject.toml").write_text(
        PYPROJECT.replace('hosts = ["desktop", "server"]', 'hosts = ["server"]'),
        encoding="utf-8",
    )
    assert "HOST001" in {item.rule for item in check_project(root).diagnostics}
