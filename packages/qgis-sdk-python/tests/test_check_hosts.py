"""HOST001 / HOST003: a declared host set the project or this QGIS cannot honour.

``[tool.qgis-sdk] hosts`` is the one place a plugin says which hosts it targets
(decision-52 point 1). A Desktop-only declaration in a project that does not
declare Desktop is ``HOST001``; a server host declared against a QGIS built
without QGIS Server is ``HOST003``, a warning because the project is not what is
missing (decision-52 implementation note, TASK-80).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import qgis_sdk_tools.check.hosts as hosts_module
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.check.hosts import check_declared_hosts, check_hosts
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


def test_no_qgis_at_all_is_not_a_finding_about_the_plugin() -> None:
    # The workspace's pure environment has no QGIS on the path, which is a
    # statement about this interpreter, not about the project.
    assert hosts_module.qgis_server_state() is None


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
