"""Vendoring pure-Python distributions: what is copied, and what is refused.

decision-50 point 2 (TASK-77 AC #2): ``[tool.qgis-sdk.build] vendor`` copies an
installed pure-Python distribution under ``<plugin>/_vendor/`` with its
licence in ``_vendor/LICENSES/`` and its name and version in the NOTICE;
imports of the vendored roots are rewritten the way the runtime's are, in the
plugin's sources *and* inside the vendored code. A distribution carrying a
compiled extension is ``DEP003``; one whose requirement is neither vendored
nor external is ``DEP004`` naming it. The fixtures are real distributions in a
temporary site directory, so nothing is mocked: metadata is read the way
``build`` reads a user's environment.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

import distributions
import pytest
from qgis_sdk_tools.bundle import build_plugin
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.distributions import QGisSdkDistributionError, read_distribution
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

PLUGIN = "field_tools"


def never_run(argv: Sequence[str], cwd: Path) -> int:
    raise AssertionError(f"no process expected, got {argv} in {cwd}")


@pytest.fixture
def site(tmp_path: Path) -> Path:
    """A site directory the interpreter's metadata search sees."""
    directory = tmp_path / "site"
    directory.mkdir()
    return directory


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project" / PLUGIN
    write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
    return root


def declare(root: Path, build: str) -> None:
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8") + f"\n[tool.qgis-sdk.build]\n{build}\n",
        encoding="utf-8",
    )


def rules(root: Path) -> list[tuple[str, str]]:
    return [(d.rule, d.message) for d in check_project(root).diagnostics]


def entries(result_archive: Path) -> list[str]:
    with zipfile.ZipFile(result_archive) as zf:
        return zf.namelist()


def read(archive: Path, name: str) -> str:
    with zipfile.ZipFile(archive) as zf:
        return zf.read(name).decode("utf-8")


class TestDistributionMetadata:
    def test_a_pure_distribution_is_read_from_its_metadata(self, site: Path) -> None:
        distributions.install_fixture(
            site,
            "fixture-pure",
            source="from fixture_dep import answer\n",
            requires=("fixture-dep>=1",),
        )

        distribution = read_distribution("fixture-pure")

        assert distribution.name == "fixture-pure"
        assert distribution.version == "1.0"
        assert distribution.roots == ("fixture_pure",)
        assert distribution.is_pure
        assert distribution.compiled == ()
        assert distribution.requires == ("fixture-dep",)
        assert [path.name for path in distribution.licences] == ["LICENSE"]

    def test_a_compiled_distribution_names_its_extension(self, site: Path) -> None:
        distributions.install_fixture(site, "fixture-compiled", compiled=True)

        distribution = read_distribution("fixture-compiled")

        assert not distribution.is_pure
        assert [path.as_posix() for path in distribution.compiled] == [
            "fixture_compiled/_native.so"
        ]

    def test_an_uninstalled_distribution_says_where_the_copy_comes_from(
        self, site: Path
    ) -> None:
        with pytest.raises(QGisSdkDistributionError) as caught:
            read_distribution("fixture-never-installed")

        assert "is not installed in this environment" in str(caught.value)


class TestRefusals:
    def test_a_compiled_distribution_is_dep003(self, project: Path, site: Path) -> None:
        distributions.install_fixture(site, "fixture-compiled", compiled=True)
        declare(project, 'vendor = ["fixture-compiled"]')

        findings = rules(project)

        dep003 = [message for rule, message in findings if rule == "DEP003"]
        assert len(dep003) == 1
        assert "fixture-compiled" in dep003[0]
        assert "_native.so" in dep003[0]

    def test_a_missing_distribution_is_dep004(self, project: Path) -> None:
        declare(project, 'vendor = ["fixture-never-installed"]')

        findings = rules(project)

        dep004 = [message for rule, message in findings if rule == "DEP004"]
        assert len(dep004) == 1
        assert "fixture-never-installed" in dep004[0]

    def test_a_missing_transitive_requirement_is_dep004_naming_it(
        self, project: Path, site: Path
    ) -> None:
        distributions.install_fixture(
            site, "fixture-pure", requires=("fixture-absent>=2",)
        )
        declare(project, 'vendor = ["fixture-pure"]')

        findings = rules(project)

        dep004 = [message for rule, message in findings if rule == "DEP004"]
        assert len(dep004) == 1
        assert "fixture-pure" in dep004[0]
        assert "fixture-absent" in dep004[0]

    def test_a_requirement_that_is_vendored_is_accepted(
        self, project: Path, site: Path
    ) -> None:
        distributions.install_fixture(
            site, "fixture-pure", requires=("fixture-dep>=2",)
        )
        distributions.install_fixture(site, "fixture-dep")
        declare(project, 'vendor = ["fixture-pure", "fixture-dep"]')

        assert [rule for rule, _ in rules(project) if rule.startswith("DEP")] == []

    def test_a_requirement_that_is_external_is_accepted(
        self, project: Path, site: Path
    ) -> None:
        distributions.install_fixture(
            site, "fixture-pure", requires=("fixture-dep>=2",)
        )
        declare(
            project,
            'vendor = ["fixture-pure"]\nexternal = ["fixture_dep"]',
        )

        assert [rule for rule, _ in rules(project) if rule.startswith("DEP")] == []


class TestBuild:
    def test_a_vendored_package_ships_with_its_licence_and_notice(
        self, project: Path, site: Path
    ) -> None:
        distributions.install_fixture(site, "fixture-pure", source="VALUE = 42\n")
        declare(project, 'vendor = ["fixture-pure"]')
        plugin = project / PLUGIN / "plugin.py"
        plugin.write_text(
            plugin.read_text(encoding="utf-8") + "\nimport fixture_pure\n",
            encoding="utf-8",
        )

        result = build_plugin(project, run=never_run)

        assert f"{PLUGIN}/_vendor/fixture_pure/__init__.py" in entries(result.archive)
        assert f"{PLUGIN}/_vendor/LICENSES/fixture-pure-1.0-LICENSE" in entries(
            result.archive
        )
        notice = read(result.archive, f"{PLUGIN}/_vendor/NOTICE")
        assert "fixture-pure 1.0" in notice
        assert "LICENSES/fixture-pure-1.0-" in notice
        assert result.vendored == ("fixture-pure",)
        # The plugin's own import moved under the vendored path.
        assert f"from {PLUGIN}._vendor import fixture_pure" in read(
            result.archive, f"{PLUGIN}/plugin.py"
        )

    def test_a_vendored_packages_own_imports_are_rewritten(
        self, project: Path, site: Path
    ) -> None:
        distributions.install_fixture(site, "fixture-dep", source="ANSWER = 42\n")
        distributions.install_fixture(
            site,
            "fixture-pure",
            source="from fixture_dep import ANSWER\n",
            requires=("fixture-dep>=1",),
        )
        declare(project, 'vendor = ["fixture-pure", "fixture-dep"]')

        result = build_plugin(project, run=never_run)

        vendored = read(result.archive, f"{PLUGIN}/_vendor/fixture_pure/__init__.py")
        assert f"from {PLUGIN}._vendor.fixture_dep import ANSWER" in vendored

    def test_an_unvendored_requirement_refuses_the_build(
        self, project: Path, site: Path
    ) -> None:
        distributions.install_fixture(
            site, "fixture-pure", requires=("fixture-absent>=2",)
        )
        declare(project, 'vendor = ["fixture-pure"]')

        from qgis_sdk_tools.bundle import QgisSdkBuildRefusedError

        with pytest.raises(QgisSdkBuildRefusedError) as caught:
            build_plugin(project, run=never_run)

        named = [d.message for d in caught.value.diagnostics if d.rule == "DEP004"]
        assert named and "fixture-absent" in named[0]
