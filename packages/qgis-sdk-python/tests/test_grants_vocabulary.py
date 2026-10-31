"""One grant vocabulary across the page and the console (decision-54, TASK-84).

The operation names are ``<service>.<operation>`` and the grant names come from
:func:`qgis_sdk.bridge.host.host_grant_names`, so both tables accept the same
thing and refuse the same thing with the same ``GRANT001``. ``check --grants``
prints the client × operation matrix that makes the difference visible; the
plugin HTTP allowlist is shown beside them because it is authority too, and
because it names actions rather than operations.
"""

from __future__ import annotations

from pathlib import Path

from qgis_sdk.bridge.host import host_grant_names, host_operation_ids
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.grants import grants_matrix
from qgis_sdk_tools.project import load_project
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

runner = CliRunner()

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


def project(tmp_path: Path, *, extra: str = "") -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text("app = None\n")
    (root / "pyproject.toml").write_text(PYPROJECT + extra)
    return root


def config_of(root: Path):
    config, findings = load_project(root)
    assert config is not None
    return config, findings


def test_both_tables_accept_a_grant_and_an_operation_id(tmp_path: Path) -> None:
    root = project(
        tmp_path,
        extra=(
            '\n[tool.qgis-sdk.web]\nplacement = "dock"\n'
            'grants = ["layers.read", "project.layer_ids"]\n'
            '\n[tool.qgis-sdk.console]\ngrants = ["layers.read", "project.layer_ids"]\n'
        ),
    )

    assert check_project(root).diagnostics == ()


def test_one_unknown_name_is_the_same_finding_in_either_table(tmp_path: Path) -> None:
    root = project(
        tmp_path,
        extra=(
            '\n[tool.qgis-sdk.web]\nplacement = "dock"\ngrants = ["layers.nope"]\n'
            '\n[tool.qgis-sdk.console]\ngrants = ["layers.nope"]\n'
        ),
    )

    report = check_project(root)
    found = [d for d in report.diagnostics if d.rule == "GRANT001"]

    assert len(found) == 2
    assert "[tool.qgis-sdk.web] grants names `layers.nope`" in found[0].message
    assert "[tool.qgis-sdk.console] grants names `layers.nope`" in found[1].message
    for diagnostic in found:
        assert "layers.read" in diagnostic.remediation
        assert "layers.list" in diagnostic.remediation


def test_the_console_is_every_operation_until_it_says_otherwise(
    tmp_path: Path,
) -> None:
    root = project(tmp_path, extra='\n[tool.qgis-sdk.web]\nplacement = "dock"\n')

    config, findings = config_of(root)
    matrix = grants_matrix(config)

    assert findings == ()
    assert config.console.unrestricted
    assert matrix.granted("console") == host_operation_ids()
    assert matrix.granted("page") == ()


def test_a_narrowed_console_reaches_what_its_grants_name(tmp_path: Path) -> None:
    root = project(
        tmp_path,
        extra='\n[tool.qgis-sdk.console]\ngrants = ["layers.read"]\n',
    )

    config, _ = config_of(root)
    matrix = grants_matrix(config)
    granted = matrix.granted("console")

    assert "layers.list" in granted
    assert "layers.get" in granted
    assert "layers.open_vector" not in granted  # `layers.open` is its own grant
    assert "project.layer_ids" not in granted
    assert not config.console.unrestricted


def test_the_matrix_prints_three_clients_and_names_actions_for_http(
    tmp_path: Path,
) -> None:
    root = project(
        tmp_path,
        extra=('\n[tool.qgis-sdk.web]\nplacement = "dock"\ngrants = ["layers.list"]\n'),
    )

    rendered = grants_matrix(config_of(root)[0]).render()

    assert "one vocabulary, one name per operation" in rendered
    assert "PluginHttpServer(actions=...)" in rendered
    assert "plugin action and stream ids, not host operations" in rendered
    for operation in host_operation_ids():
        assert operation in rendered
    for grant in host_grant_names():
        assert grant in rendered


def test_the_matrix_says_when_no_page_is_declared(tmp_path: Path) -> None:
    root = project(tmp_path)

    matrix = grants_matrix(config_of(root)[0])

    assert not matrix.page_declared
    assert matrix.granted("page") == ()
    assert "no [tool.qgis-sdk.web] is declared" in matrix.render()


def test_a_console_key_that_does_not_exist_is_config001(tmp_path: Path) -> None:
    root = project(
        tmp_path, extra='\n[tool.qgis-sdk.console]\nallow = ["layers.read"]\n'
    )

    report = check_project(root)

    (found,) = report.diagnostics
    assert found.rule == "CONFIG001"
    assert "`allow`" in found.message


def test_check_grants_prints_the_matrix(tmp_path: Path) -> None:
    root = project(
        tmp_path,
        extra='\n[tool.qgis-sdk.console]\ngrants = ["layers.read"]\n',
    )
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["check", str(root), "--grants"], obj=runtime)

    assert result.exit_code == 0, result.output
    assert "grants: one vocabulary" in runtime.stdout
    assert "layers.list" in runtime.stdout
    assert "checked 2 files: no problems" in runtime.stdout


def test_a_broken_grant_does_not_stop_the_matrix(tmp_path: Path) -> None:
    root = project(
        tmp_path,
        extra='\n[tool.qgis-sdk.console]\ngrants = ["layers.nope", "layers.read"]\n',
    )
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["check", str(root), "--grants"], obj=runtime)

    assert result.exit_code == 1
    assert "GRANT001" in runtime.stdout
    assert "layers.list" in runtime.stdout  # the matrix still printed
