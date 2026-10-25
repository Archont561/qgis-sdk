"""``check``'s version rules: a runtime pin or a generated client outside what this
tools release supports (TASK-57, decision-35)."""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.bridge.protocol import HOST_SCHEMA_VERSION
from qgis_sdk.declarations import PLUGIN_DESCRIPTION_SCHEMA_VERSION
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.check import versions as versions_module
from qgis_sdk_tools.check.versions import (
    RuntimeRange,
    requirement_admits_range,
    supported_runtime_range,
)
from test_check_project import METADATA, codes


def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from .plugin import classFactory\n")
    (package / "plugin.py").write_text("import os\n")
    (package / "metadata.txt").write_text(METADATA)
    return root


@pytest.fixture
def supported(monkeypatch: pytest.MonkeyPatch) -> RuntimeRange:
    """Pin what "this tools release supports" so the tests do not track the tree."""
    rng = RuntimeRange(lower="0.5.0", upper="0.6")
    monkeypatch.setattr(versions_module, "supported_runtime_range", lambda: rng)
    return rng


def test_the_supported_range_is_read_from_the_tools_distribution() -> None:
    rng = supported_runtime_range()

    # Whether installed or run from the checkout, the tools know their range.
    assert rng is not None
    assert rng.lower.count(".") == 2 and rng.upper.count(".") == 1
    assert rng.as_requirement().startswith("qgis-sdk-runtime>=")


def test_installed_metadata_normalizes_the_clause_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``importlib.metadata`` hands back ``<0.5,>=0.4.0``; both orders must read."""
    monkeypatch.setattr(
        versions_module.importlib.metadata,
        "requires",
        lambda name: ["qgis-sdk-runtime<0.5,>=0.4.0", "typer==0.27.3"],
    )

    assert supported_runtime_range() == RuntimeRange(lower="0.4.0", upper="0.5")


@pytest.mark.parametrize(
    ("specifier", "admits"),
    [
        ("", True),
        ("==0.5.2", True),
        ("==0.5.0", True),
        ("==0.4.0", False),
        ("==0.6.0", False),
        (">=0.4.0,<0.5", False),
        (">=0.4.0,<0.6", True),
        (">=0.5.9", True),
        (">=0.6.0", False),
        ("<0.5.0", False),
        ("<=0.5.0", True),
        ("~=0.5.1", True),
        ("~=0.4.0", False),
        ("==0.5.*", True),
        ("==0.4.*", False),
        ("!=0.5.0", True),
        (">0.5.0,<0.5.1", True),
    ],
)
def test_requirement_admits_range(specifier: str, admits: bool) -> None:
    rng = RuntimeRange(lower="0.5.0", upper="0.6")
    assert requirement_admits_range(specifier, rng) is admits


def test_a_runtime_pin_outside_the_supported_range_is_reported(
    tmp_path: Path, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "field-tools"\nversion = "0"\n'
        'dependencies = ["qgis-sdk-runtime==0.4.0"]\n'
    )

    report = check_project(root)

    assert codes(report) == ["VERSION001"]
    finding = report.diagnostics[0]
    assert finding.path == Path("pyproject.toml")
    assert "qgis-sdk-runtime==0.4.0" in finding.message
    assert ">=0.5.0,<0.6" in finding.message
    assert "qgis-sdk-tools" in finding.remediation


def test_the_kit_and_extras_and_dependency_groups_count_as_runtime_pins(
    tmp_path: Path, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "field-tools"\nversion = "0"\n'
        'dependencies = ["qgis-sdk[controlled-deployment]==0.3.0", "typer"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["qgis-sdk-runtime>=0.4,<0.5"]\n'
        "[dependency-groups]\n"
        'test = ["qgis-sdk-runtime>=0.5.1", {include-group = "other"}]\n'
        "other = []\n"
    )

    report = check_project(root)

    messages = [d.message for d in report.diagnostics if d.rule == "VERSION001"]
    assert len(messages) == 2
    assert any("qgis-sdk[controlled-deployment]==0.3.0" in m for m in messages)
    assert any("qgis-sdk-runtime>=0.4,<0.5" in m for m in messages)


def test_a_pin_inside_the_range_and_no_pin_at_all_pass(
    tmp_path: Path, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    assert "VERSION001" not in codes(check_project(root))

    (root / "pyproject.toml").write_text(
        '[project]\nname = "field-tools"\nversion = "0"\n'
        'dependencies = ["qgis-sdk-runtime>=0.5.0,<0.6"]\n'
    )
    assert "VERSION001" not in codes(check_project(root))


def test_an_unknown_range_skips_the_rule_rather_than_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(versions_module, "supported_runtime_range", lambda: None)
    root = project(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["qgis-sdk-runtime==0.0.1"]\n'
    )

    assert "VERSION001" not in codes(check_project(root))


def _generated_client(root: Path, *, description: int, host: int | None = None) -> Path:
    target = root / "web" / "src" / "generated"
    target.mkdir(parents=True)
    client = target / "client.ts"
    client.write_text(
        "// Generated by qgis-sdk. Do not edit.\n"
        "// Source: field_tools.plugin:FieldTools\n\n"
        f"export const PLUGIN_DESCRIPTION_SCHEMA_VERSION = {description};\n"
    )
    if host is not None:
        (target / "host.ts").write_text(
            "// Generated by qgis-sdk. Do not edit.\n\n"
            f"export const HOST_SCHEMA_VERSION = {host};\n"
        )
    return client


def test_a_generated_client_from_another_contract_version_is_reported(
    tmp_path: Path,
) -> None:
    root = project(tmp_path)
    client = _generated_client(
        root,
        description=PLUGIN_DESCRIPTION_SCHEMA_VERSION + 1,
        host=HOST_SCHEMA_VERSION + 1,
    )

    report = check_project(root)

    version_findings = [d for d in report.diagnostics if d.rule == "VERSION002"]
    assert [d.path for d in version_findings] == [
        client.relative_to(root),
        Path("web/src/generated/host.ts"),
    ]
    assert (
        f"version {PLUGIN_DESCRIPTION_SCHEMA_VERSION + 1}"
        in version_findings[0].message
    )
    assert f"version {PLUGIN_DESCRIPTION_SCHEMA_VERSION}" in version_findings[0].message
    assert "qgis-sdk bridge generate" in version_findings[0].remediation
    assert version_findings[0].line == 4


def test_a_generated_client_at_the_current_contract_version_passes(
    tmp_path: Path,
) -> None:
    root = project(tmp_path)
    _generated_client(root, description=PLUGIN_DESCRIPTION_SCHEMA_VERSION)

    assert "VERSION002" not in codes(check_project(root))


def test_generated_clients_under_node_modules_are_not_the_authors(
    tmp_path: Path,
) -> None:
    root = project(tmp_path)
    vendored = root / "web" / "node_modules" / "@archont561" / "qgis-sdk" / "x.ts"
    vendored.parent.mkdir(parents=True)
    vendored.write_text(
        "// Generated by qgis-sdk. Do not edit.\n"
        f"export const HOST_SCHEMA_VERSION = {HOST_SCHEMA_VERSION + 5};\n"
    )

    assert "VERSION002" not in codes(check_project(root))
