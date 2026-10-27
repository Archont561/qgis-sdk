"""``check``'s version rules: a runtime pin or a generated client outside what this
tools release supports (TASK-57, decision-35)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from packaging.specifiers import SpecifierSet
from packaging.version import Version as PackagingVersion
from qgis_sdk.bridge.protocol import HOST_SCHEMA_VERSION
from qgis_sdk.declarations import PLUGIN_DESCRIPTION_SCHEMA_VERSION
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.check import versions as versions_module
from qgis_sdk_tools.check.versions import (
    RuntimeRange,
    requirement_admits_range,
    supported_runtime_range,
)
from test_check_project import PYPROJECT, codes

#: The [project]/[tool.qgis-sdk] tables without a runtime requirement, so a
#: test writes exactly the dependency lines it is about.
BASE = PYPROJECT.replace('dependencies = ["qgis-sdk-runtime>=0.1,<99"]\n', "")


AUTHORS = 'authors = [{ name = "Jane", email = "jane@example.org" }]\n'


def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text("import os\n")
    (root / "pyproject.toml").write_text(BASE)
    return root


def declare(root: Path, lines: str) -> None:
    """Write the project manifest with ``lines`` inside ``[project]``."""
    (root / "pyproject.toml").write_text(BASE.replace(AUTHORS, AUTHORS + lines))


# -- strategies: release versions and the specifier grammar the rule reads ------

#: Small segments keep the shrunk counterexamples readable and the padding rules
#: (``0.5`` == ``0.5.0``) exercised.
segments = st.lists(st.integers(0, 9), min_size=1, max_size=3)
release_versions = segments.map(lambda parts: ".".join(map(str, parts)))
#: ``~=`` needs two segments and ``==X.*`` is its own clause shape.
_two_plus = st.lists(st.integers(0, 9), min_size=2, max_size=3).map(
    lambda parts: ".".join(map(str, parts))
)
clauses = st.one_of(
    st.tuples(
        st.sampled_from(["==", "!=", ">=", "<=", ">", "<"]), release_versions
    ).map("".join),
    _two_plus.map(lambda v: f"~={v}"),
    release_versions.map(lambda v: f"=={v}.*"),
    release_versions.map(lambda v: f"!={v}.*"),
)
specifiers = st.lists(clauses, min_size=0, max_size=3).map(",".join)


def oracle_admits(specifier: str, version: str) -> bool:
    """What ``packaging`` says; the arithmetic under test must agree."""
    return SpecifierSet(specifier).contains(PackagingVersion(version), prereleases=True)


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


@given(specifier=specifiers, inside=release_versions)
@settings(max_examples=60, deadline=None, derandomize=True)
@example(specifier="", inside="0.5.0")
@example(specifier=">=0.4.0,<0.6", inside="0.5.0")
@example(specifier="~=0.5.1", inside="0.5.1")
@example(specifier="==0.5.*", inside="0.5.0")
def test_a_specifier_some_supported_version_satisfies_admits_the_range(
    specifier: str, inside: str
) -> None:
    """Soundness: a point ``packaging`` admits inside the range means the
    range arithmetic must admit the specifier too (it may admit more: ``!=``
    is ignored there on purpose)."""
    rng = RuntimeRange(lower="0.5.0", upper="0.6")
    lower = PackagingVersion(rng.lower)
    upper = PackagingVersion(rng.upper)
    if not (lower <= PackagingVersion(inside) < upper):
        return
    if oracle_admits(specifier, inside):
        assert requirement_admits_range(specifier, rng) is True


@pytest.mark.parametrize(
    ("specifier", "admits"),
    [
        ("==0.4.0", False),
        ("==0.6.0", False),
        (">=0.4.0,<0.5", False),
        (">=0.6.0", False),
        ("<0.5.0", False),
        ("~=0.4.0", False),
        ("==0.4.*", False),
        ("!=0.5.0", True),  # `!=` alone never empties a range
        ("@@@", True),  # a syntax the arithmetic does not know is never reported
    ],
)
def test_requirement_admits_range_refuses_what_lies_outside(
    specifier: str, admits: bool
) -> None:
    rng = RuntimeRange(lower="0.5.0", upper="0.6")
    assert requirement_admits_range(specifier, rng) is admits


def test_a_runtime_pin_outside_the_supported_range_is_reported(
    tmp_path: Path, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    declare(root, 'dependencies = ["qgis-sdk-runtime==0.4.0"]\n')

    report = check_project(root)

    assert "VERSION001" in codes(report)
    finding = next(d for d in report.diagnostics if d.rule == "VERSION001")
    assert finding.path == Path("pyproject.toml")
    assert "qgis-sdk-runtime==0.4.0" in finding.message
    assert ">=0.5.0,<0.6" in finding.message
    assert "qgis-sdk-tools" in finding.remediation


def test_the_kit_and_extras_and_dependency_groups_count_as_runtime_pins(
    tmp_path: Path, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    (root / "pyproject.toml").write_text(
        BASE.replace(
            AUTHORS,
            AUTHORS
            + 'dependencies = ["qgis-sdk[controlled-deployment]==0.3.0", "typer"]\n'
            "[project.optional-dependencies]\n"
            'dev = ["qgis-sdk-runtime>=0.4,<0.5"]\n'
            "[dependency-groups]\n"
            'test = ["qgis-sdk-runtime>=0.5.1", {include-group = "other"}]\n'
            "other = []\n",
        )
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

    declare(root, 'dependencies = ["qgis-sdk-runtime>=0.5.0,<0.6"]\n')
    assert "VERSION001" not in codes(check_project(root))


def test_an_unknown_range_skips_the_rule_rather_than_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(versions_module, "supported_runtime_range", lambda: None)
    root = project(tmp_path)
    declare(root, 'dependencies = ["qgis-sdk-runtime==0.0.1"]\n')

    assert "VERSION001" not in codes(check_project(root))


# --- VERSION003/VERSION004: the project's own requirement vs the installed runtime


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(versions_module, "installed_runtime_version", lambda: "0.5.2")
    return "0.5.2"


@given(specifier=specifiers, version=release_versions)
@settings(max_examples=80, deadline=None, derandomize=True)
@example(specifier=">=0.5,<0.6", version="0.5.2")
@example(specifier="==0.5.*", version="0.6.0")
@example(specifier="!=0.5.*", version="0.6.1")
@example(specifier="~=0.5.1", version="0.6.0")
@example(specifier="==0.5", version="0.5.0")  # zero padding
def test_requirement_admits_version_agrees_with_packaging(
    specifier: str, version: str
) -> None:
    assert versions_module.requirement_admits_version(specifier, version) is (
        oracle_admits(specifier, version)
    )


@pytest.mark.parametrize(
    ("specifier", "version"),
    [("", "1.2.3"), (">=0.5", "not-a-version"), ("@@@", "0.5.2")],
)
def test_what_the_arithmetic_cannot_read_counts_as_satisfied(
    specifier: str, version: str
) -> None:
    assert versions_module.requirement_admits_version(specifier, version) is True


def test_the_installed_runtime_version_is_known_here() -> None:
    # Installed or from the checkout: the tools always know which runtime ships.
    version = versions_module.installed_runtime_version()
    assert version is not None
    assert version.count(".") >= 1


def test_no_runtime_requirement_is_version003_as_a_warning(
    tmp_path: Path, installed: str
) -> None:
    root = project(tmp_path)

    report = check_project(root)

    (finding,) = [d for d in report.diagnostics if d.rule == "VERSION003"]
    assert finding.severity == "warning"
    assert report.ok
    assert finding.path == Path("pyproject.toml")
    assert installed in finding.message
    assert "qgis-sdk-runtime>=0.5,<0.6" in finding.remediation
    assert "VERSION004" not in codes(report)


def test_an_installed_runtime_outside_the_requirement_is_version004(
    tmp_path: Path, installed: str, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    declare(root, 'dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]\n')

    report = check_project(root)

    (finding,) = [d for d in report.diagnostics if d.rule == "VERSION004"]
    assert finding.severity == "error"
    assert not report.ok
    assert "qgis-sdk-runtime>=0.6,<0.7" in finding.message
    assert installed in finding.message
    assert 'pip install "qgis-sdk-runtime>=0.6,<0.7"' in finding.remediation
    assert "VERSION003" not in codes(report)


def test_a_satisfied_requirement_reports_neither(
    tmp_path: Path, installed: str, supported: RuntimeRange
) -> None:
    root = project(tmp_path)
    declare(root, 'dependencies = ["qgis-sdk-runtime>=0.5,<0.6"]\n')

    found = codes(check_project(root))

    assert "VERSION003" not in found
    assert "VERSION004" not in found


def test_resolve_runtime_pairs_the_requirement_with_the_installed_version(
    tmp_path: Path, installed: str
) -> None:
    root = project(tmp_path)
    declare(
        root, 'dependencies = ["typer", "qgis-sdk>=0.5,<0.6; python_version > \'3\'"]\n'
    )

    resolution = versions_module.resolve_runtime(root)

    assert resolution.requirement == "qgis-sdk>=0.5,<0.6"
    assert resolution.specifier == ">=0.5,<0.6"
    assert resolution.installed == installed
    assert resolution.satisfied

    bare = versions_module.resolve_runtime(tmp_path / "nowhere")
    assert bare.requirement is None
    assert bare.satisfied


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
