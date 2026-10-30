"""Finding a QGIS install: explicit configuration, then PATH, then this environment."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from qgis_sdk_tools.devtools import (
    QgisInstall,
    QgisSdkQgisNotFoundError,
    find_qgis_install,
    wants_headless,
)


def make_prefix(root: Path, *, executable: bool = True, conda: bool = False) -> Path:
    """Lay out the conda / Linux prefix shape: bin/qgis plus share/qgis/python."""
    prefix = root / "prefix"
    (prefix / "share" / "qgis" / "python" / "qgis").mkdir(parents=True)
    (prefix / "share" / "qgis" / "python" / "qgis" / "__init__.py").write_text("")
    (prefix / "bin").mkdir()
    (prefix / "bin" / "python").write_text("")
    if executable:
        (prefix / "bin" / "qgis").write_text("")
    if conda:
        (prefix / "conda-meta").mkdir()
    return prefix


def no_which(name: str, path: str | None = None) -> str | None:
    return None


def test_an_explicit_prefix_wins_and_names_its_source(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)

    install = find_qgis_install(
        {"QGIS_PREFIX_PATH": str(tmp_path / "elsewhere")},
        prefix=prefix,
        which=no_which,
        sys_prefix=tmp_path / "nothing",
    )

    assert install == QgisInstall(
        prefix=prefix.resolve(),
        bindings=(prefix / "share" / "qgis" / "python").resolve(),
        executable=(prefix / "bin" / "qgis").resolve(),
        python=(prefix / "bin" / "python").resolve(),
        source="the --qgis-prefix option",
        conda=False,
    )


def test_an_explicit_prefix_without_bindings_fails_instead_of_falling_through(
    tmp_path: Path,
) -> None:
    good = make_prefix(tmp_path)
    bad = tmp_path / "bad"
    bad.mkdir()

    with pytest.raises(QgisSdkQgisNotFoundError) as excinfo:
        find_qgis_install({}, prefix=bad, which=no_which, sys_prefix=good)

    message = str(excinfo.value)
    assert str(bad) in message
    assert "share/qgis/python" in message
    assert "--qgis-prefix" in message


def test_the_project_configuration_comes_before_the_environment(
    tmp_path: Path,
) -> None:
    prefix = make_prefix(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        f'[tool.qgis-sdk]\nqgis-prefix = "{prefix.as_posix()}"\n'
    )

    install = find_qgis_install(
        {"QGIS_PREFIX_PATH": str(tmp_path / "elsewhere")},
        project=project,
        which=no_which,
        sys_prefix=tmp_path / "nothing",
    )

    assert install.prefix == prefix.resolve()
    assert install.source == "pyproject.toml [tool.qgis-sdk] qgis-prefix"


def test_a_relative_configured_prefix_resolves_against_the_project(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    prefix = make_prefix(project)
    (project / "pyproject.toml").write_text('[tool.qgis-sdk]\nqgis-prefix = "prefix"\n')

    install = find_qgis_install({}, project=project, which=no_which)

    assert install.prefix == prefix.resolve()


def test_qgis_prefix_path_in_the_environment_is_honoured(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)

    install = find_qgis_install(
        {"QGIS_PREFIX_PATH": str(prefix)}, which=no_which, sys_prefix=tmp_path
    )

    assert install.prefix == prefix.resolve()
    assert install.source == "QGIS_PREFIX_PATH"


def test_qgis_on_path_locates_its_prefix(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)

    def which(name: str, path: str | None = None) -> str | None:
        assert path == "/usr/bin"
        return str(prefix / "bin" / "qgis") if name == "qgis" else None

    install = find_qgis_install(
        {"PATH": "/usr/bin"}, which=which, sys_prefix=tmp_path / "nothing"
    )

    assert install.prefix == prefix.resolve()
    assert install.executable == (prefix / "bin" / "qgis").resolve()
    assert install.source == f"qgis on PATH ({prefix / 'bin' / 'qgis'})"


def test_the_current_environment_is_the_last_resort(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path, executable=False, conda=True)

    install = find_qgis_install({}, which=no_which, sys_prefix=prefix)

    assert install.prefix == prefix.resolve()
    assert install.executable is None
    assert install.conda is True
    assert install.source == "the current Python environment"


def test_nothing_found_lists_every_place_that_was_looked_at(tmp_path: Path) -> None:
    with pytest.raises(QgisSdkQgisNotFoundError) as excinfo:
        find_qgis_install({"PATH": str(tmp_path)}, sys_prefix=tmp_path / "env")

    message = str(excinfo.value)
    assert "QGIS_PREFIX_PATH" in message
    assert "PATH" in message
    assert str(tmp_path / "env") in message
    assert "--qgis-prefix" in message
    assert "pip install" not in message


def test_osgeo4w_layout_is_recognised(tmp_path: Path) -> None:
    prefix = tmp_path / "OSGeo4W"
    (prefix / "apps" / "qgis" / "python" / "qgis").mkdir(parents=True)
    (prefix / "apps" / "qgis" / "python" / "qgis" / "__init__.py").write_text("")
    (prefix / "bin").mkdir()
    (prefix / "bin" / "qgis-bin.exe").write_text("")

    install = find_qgis_install({}, prefix=prefix, which=no_which)

    assert install.bindings == (prefix / "apps" / "qgis" / "python").resolve()
    assert install.executable == (prefix / "bin" / "qgis-bin.exe").resolve()


class TestEnvironment:
    def test_the_subprocess_environment_prepends_bindings_and_names_the_prefix(
        self, tmp_path: Path
    ) -> None:
        prefix = make_prefix(tmp_path)
        (prefix / "share" / "proj").mkdir()
        install = find_qgis_install({}, prefix=prefix, which=no_which)

        env = install.environment(
            {"PYTHONPATH": "/already", "HOME": "/home/x"}, extra_paths=(tmp_path,)
        )

        assert env["HOME"] == "/home/x"
        assert env["PYTHONPATH"].split(os.pathsep) == [
            str(install.bindings),
            str(tmp_path),
            "/already",
        ]
        assert env["QGIS_PREFIX_PATH"] == str(install.prefix)
        assert env["PROJ_LIB"] == str(prefix.resolve() / "share" / "proj")
        assert "PYTHONHOME" not in env

    def test_headless_adds_the_offscreen_platform_and_a_placeholder_display(
        self, tmp_path: Path
    ) -> None:
        install = find_qgis_install({}, prefix=make_prefix(tmp_path), which=no_which)

        env = install.environment({}, headless=True)

        assert env["QT_QPA_PLATFORM"] == "offscreen"
        assert env["DISPLAY"] == ":99"
        assert "--disable-gpu" in env["QTWEBENGINE_CHROMIUM_FLAGS"]

    def test_a_platform_the_user_chose_is_kept(self, tmp_path: Path) -> None:
        install = find_qgis_install({}, prefix=make_prefix(tmp_path), which=no_which)

        env = install.environment({"QT_QPA_PLATFORM": "xcb"}, headless=True)

        assert env["QT_QPA_PLATFORM"] == "xcb"

    def test_a_conda_prefix_pins_pythonhome_for_the_desktop_binary_only(
        self, tmp_path: Path
    ) -> None:
        install = find_qgis_install(
            {}, prefix=make_prefix(tmp_path, conda=True), which=no_which
        )

        assert install.environment({}, desktop=True)["PYTHONHOME"] == str(
            install.prefix
        )
        assert "PYTHONHOME" not in install.environment({})


@pytest.mark.parametrize(
    ("env", "platform", "expected"),
    [
        ({}, "linux", True),
        ({"DISPLAY": ":0"}, "linux", False),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", False),
        ({"QT_QPA_PLATFORM": "offscreen"}, "linux", True),
        ({"QT_QPA_PLATFORM": "xcb"}, "linux", False),
        ({}, "darwin", False),
        ({}, "win32", False),
        ({"QT_QPA_PLATFORM": "offscreen"}, "win32", True),
    ],
)
def test_headless_means_no_display_to_show_a_window_on(
    env: dict[str, str], platform: str, expected: bool
) -> None:
    assert wants_headless(env, platform=platform) is expected


def test_a_debian_prefix_finds_the_distributions_dist_packages(tmp_path: Path) -> None:
    """`apt install python3-qgis` puts `qgis` in `lib/python3/dist-packages`.

    No `share/qgis/python` exists on such an install, so a discovery that only
    knew the conda and OSGeo4W layouts refused `/usr` - the prefix the qgis.org
    and Debian packages install into, and the one the `QGIS 3.44 LTS` row runs.
    """
    prefix = tmp_path / "usr"
    package = prefix / "lib" / "python3" / "dist-packages" / "qgis"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (prefix / "bin").mkdir()
    (prefix / "bin" / "qgis").write_text("")
    (prefix / "bin" / "python3").write_text("")

    install = find_qgis_install(
        {}, prefix=prefix, which=no_which, sys_prefix=tmp_path / "nothing"
    )

    assert install.bindings == (prefix / "lib" / "python3" / "dist-packages").resolve()
    assert install.python == (prefix / "bin" / "python3").resolve()
    assert install.source == "the --qgis-prefix option"
