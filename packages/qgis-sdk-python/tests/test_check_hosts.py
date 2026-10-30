"""HOST001 / HOST002 / HOST003: a declared host set that cannot be honoured.

``[tool.qgis-sdk] hosts`` is the one place a plugin says which hosts it targets
(decision-52 point 1). A Desktop-only declaration in a project that does not
declare Desktop is ``HOST001``, a server hook in a project that does not declare
the server is ``HOST002``, and a server host declared against a QGIS built
without QGIS Server is ``HOST003`` - a warning, because the project is not what is
missing (decision-52 implementation note, TASK-80).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import qgis_sdk_tools.check.hosts as hosts_module
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.check.hosts import (
    check_declared_hosts,
    check_hosts,
    qgis_server_state,
)
from qgis_sdk_tools.project import load_project

PYPROJECT = """[project]
name = "field-tools"
version = "0.1.0"
description = "Field tools."
authors = [{ name = "Jane", email = "jane@example.org" }]
dependencies = ["qgis-sdk-runtime>=0.1,<99"]

[tool.qgis-sdk]
plugin = "field_tools.plugin:app"
qgis-minimum-version = "3.40"
"""


@pytest.fixture(autouse=True)
def no_visible_qgis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer ``HOST003`` from the test, not from the machine running it.

    Whether this interpreter can see a QGIS with server bindings is a property
    of the environment, so a test that does not stub it would pass on one
    machine and fail on the next. ``None`` is the honest default - no QGIS
    visible, so nothing to say - and each HOST003 test says what it means.
    """
    monkeypatch.setattr(hosts_module, "qgis_server_state", lambda: None)


def project(tmp_path: Path, *, extra: str = "", source: str = "import os\n") -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text(textwrap.dedent(source), encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT + extra, encoding="utf-8")
    return root


def found(source: str, *, hosts: tuple[str, ...] = ("server",)) -> list[str]:
    return [
        f"{d.rule}:{d.line}:{d.message}"
        for d in check_hosts(
            textwrap.dedent(source), path=Path("field_tools/plugin.py"), hosts=hosts
        )
    ]


# -- [tool.qgis-sdk] hosts is read and validated (CONFIG001) ------------------------


def test_hosts_defaults_to_the_desktop(tmp_path: Path) -> None:
    config, findings = load_project(project(tmp_path))

    assert findings == ()
    assert config is not None and config.hosts == ("desktop",)


def test_a_declared_host_set_is_read_in_order_without_repeats(tmp_path: Path) -> None:
    root = project(tmp_path, extra='\nhosts = ["server", "app", "server"]\n')

    config, findings = load_project(root)

    assert findings == ()
    assert config is not None and config.hosts == ("server", "app")


def test_a_host_name_outside_the_three_is_config001(tmp_path: Path) -> None:
    root = project(tmp_path, extra='\nhosts = ["desktop", "mobile"]\n')

    _, findings = load_project(root)

    assert [(d.rule, "mobile" in d.message) for d in findings] == [("CONFIG001", True)]


def test_hosts_that_is_not_a_list_is_config001(tmp_path: Path) -> None:
    root = project(tmp_path, extra='\nhosts = "server"\n')

    config, findings = load_project(root)

    assert [d.rule for d in findings] == ["CONFIG001"]
    assert config is not None and config.hosts == ("desktop",)


# -- HOST001: a Desktop-only declaration on a plugin without Desktop -----------------


def test_a_toolbar_binding_on_a_server_only_plugin_is_a_finding() -> None:
    source = """
        from qgis_sdk import QgisSdkPlugin, toolbar

        app = QgisSdkPlugin(id="field_tools", title="Field Tools")

        @toolbar
        @app.action(id="ping", title="Ping")
        def ping(ctx) -> None: ...
        """

    expected = (
        "HOST001:6:the `@toolbar` binding on `ping` needs the Desktop host, "
        + "but `[tool.qgis-sdk] hosts` declares server"
    )
    assert found(source) == [expected]


def test_the_import_alias_spelling_is_recognised_too() -> None:
    source = """
        from qgis_sdk import QgisSdkPlugin
        from qgis_sdk import menu as ribbon

        app = QgisSdkPlugin(id="field_tools", title="Field Tools")

        @ribbon("Vector/Field Tools")
        @app.action(id="ping", title="Ping")
        def ping(ctx) -> None: ...
        """

    assert [item.split(":", 1)[0] for item in found(source)] == ["HOST001"]


def test_a_dialog_surface_on_a_server_only_plugin_is_a_finding() -> None:
    source = """
        from qgis_sdk.ui import Dialog

        class PingDialog(Dialog):
            def build(self): ...
        """

    messages = found(source)
    assert len(messages) == 1
    assert "the `PingDialog` Dialog surface" in messages[0]


def test_a_project_that_declares_desktop_answers_for_nothing() -> None:
    source = """
        from qgis_sdk import toolbar

        @toolbar
        def ping(ctx) -> None: ...
        """

    assert found(source, hosts=("desktop", "server")) == []


def test_a_plain_module_has_nothing_to_answer_for() -> None:
    source = """
        from qgis_sdk.ui import Dialog

        class Helper:
            def build(self): ...
        """

    assert found(source) == []


# -- HOST001 from the project, and HOST003 from the environment ---------------------


def test_a_web_view_without_the_desktop_host_is_a_finding(tmp_path: Path) -> None:
    root = project(tmp_path, extra='\nhosts = ["server"]\n\n[tool.qgis-sdk.web]\n')

    config, findings = load_project(root)
    assert findings == ()
    assert config is not None

    reported = [f"{d.rule}:{d.path.as_posix()}" for d in check_declared_hosts(config)]
    assert reported == ["HOST001:pyproject.toml"]


def _stub_server_state(monkeypatch: pytest.MonkeyPatch, state: bool | None) -> None:
    monkeypatch.setattr(hosts_module, "qgis_server_state", lambda: state)


def test_a_server_host_without_qgis_server_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_server_state(monkeypatch, False)
    root = project(tmp_path, extra='\nhosts = ["server"]\n')
    config, _ = load_project(root)
    assert config is not None

    reported = list(check_declared_hosts(config))

    assert [d.rule for d in reported] == ["HOST003"]
    assert reported[0].severity == "warning"
    assert "built without QGIS Server" in reported[0].message


@pytest.mark.parametrize("state", [True, None])
def test_a_server_host_is_silent_when_the_environment_cannot_be_blamed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, state: bool | None
) -> None:
    _stub_server_state(monkeypatch, state)
    root = project(tmp_path, extra='\nhosts = ["server"]\n')
    config, _ = load_project(root)
    assert config is not None

    assert list(check_declared_hosts(config)) == []


def _visible_qgis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Make ``find_spec("qgis")`` answer with a package under ``tmp_path``."""
    import importlib.util
    import types

    package = tmp_path / "qgis"
    package.mkdir()
    spec = types.SimpleNamespace(submodule_search_locations=[str(package)])

    def find_spec(name: str, *args: object, **kwargs: object) -> object:
        return spec if name == "qgis" else None

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    return package


def test_the_probe_reads_the_installation_without_importing_qgis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _visible_qgis(monkeypatch, tmp_path)
    (package / "server").mkdir()
    (package / "server" / "__init__.py").write_text("")

    assert qgis_server_state() is True


def test_the_probe_finds_a_compiled_server_module_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _visible_qgis(monkeypatch, tmp_path)
    (package / "_server.cpython-314-x86_64-linux-gnu.so").write_bytes(b"")

    assert qgis_server_state() is True


def test_a_qgis_without_server_bindings_answers_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _visible_qgis(monkeypatch, tmp_path)

    assert qgis_server_state() is False


def test_no_qgis_at_all_is_not_a_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)

    assert qgis_server_state() is None


# -- end to end through check_project ----------------------------------------------


def test_check_project_reports_a_desktop_binding_on_a_server_plugin(
    tmp_path: Path,
) -> None:
    root = project(
        tmp_path,
        extra='\nhosts = ["server"]\n',
        source="""
            from qgis_sdk import QgisSdkPlugin, toolbar

            app = QgisSdkPlugin(id="field_tools", title="Field Tools")

            @toolbar
            @app.action(id="ping", title="Ping")
            def ping(ctx) -> None: ...
            """,
    )

    report = check_project(root)

    assert [d.rule for d in report.diagnostics] == ["HOST001"]
    assert not report.ok


def test_a_host003_warning_does_not_fail_the_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_server_state(monkeypatch, False)
    root = project(tmp_path, extra='\nhosts = ["server"]\n')

    report = check_project(root)

    assert [d.rule for d in report.diagnostics] == ["HOST003"]
    assert report.ok  # a warning: the project is fine, this QGIS is not


# -- HOST002: a server hook on a plugin without the server host ----------------------


def test_a_server_hook_on_a_desktop_only_plugin_is_a_finding() -> None:
    source = """
        from qgis_sdk.server import ServerContext, ServerResponse, filter

        @filter(priority=10)
        def default_version(ctx: ServerContext, request, response): ...
        """

    expected = (
        "HOST002:4:the `@server.filter` hook on `default_version` needs the "
        + "server host, but `[tool.qgis-sdk] hosts` declares desktop"
    )
    assert found(source, hosts=("desktop",)) == [expected]


@pytest.mark.parametrize("attribute", ["service", "access_control"])
def test_every_server_decorator_is_recognised(attribute: str) -> None:
    source = f"""
        from qgis_sdk.server import {attribute}

        @{attribute}(priority=1)
        def hook(ctx, request, response): ...
        """

    assert [item.split(":", 1)[0] for item in found(source, hosts=("desktop",))] == [
        "HOST002"
    ]


def test_the_module_alias_spelling_is_recognised_too() -> None:
    # `import qgis_sdk.server as srv` is the same declaration as the from-import.
    source = """
        import qgis_sdk.server as srv

        @srv.service(name="SDKDEMO")
        def demo(ctx, request): ...
        """

    assert [item.split(":", 1)[0] for item in found(source, hosts=("desktop",))] == [
        "HOST002"
    ]


def test_a_project_that_declares_the_server_answers_for_nothing() -> None:
    source = """
        from qgis_sdk.server import filter

        @filter(priority=10)
        def default_version(ctx, request, response): ...
        """

    assert found(source, hosts=("desktop", "server")) == []


def test_a_plugin_declaring_neither_host_answers_for_both_kinds() -> None:
    source = """
        from qgis_sdk import toolbar
        from qgis_sdk.server import access_control

        @toolbar
        def ping(ctx) -> None: ...

        @access_control(priority=1)
        def only_public(ctx, request, layer) -> bool: ...
        """

    assert [item.split(":", 1)[0] for item in found(source, hosts=("app",))] == [
        "HOST001",
        "HOST002",
    ]


def test_a_filter_from_somewhere_else_is_not_a_server_hook() -> None:
    # `filter` and `service` are ordinary words; only the module they come from
    # makes a declaration a server hook.
    source = """
        from itertools import filterfalse

        @filterfalse
        def odd(value) -> bool: ...
        """

    assert found(source, hosts=("desktop",)) == []
