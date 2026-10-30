"""The support matrix is one machine-readable source (TASK-9 AC 2): the rows the
kit is qualified on, the host it runs on, and the docs rendered from the same
data."""

from __future__ import annotations

import json
import re
from pathlib import Path

from qgis_sdk_tools import targets as targets_module
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.targets import (
    SUPPORT_MATRIX,
    Host,
    Target,
    describe_host,
    qualified_target,
    render_markdown,
    version_prefix,
)
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "apps" / "docs" / "guides" / "doc-12 - qgis-sdk-Python-package-guide.md"

LINUX = Host(
    os="linux", arch="x86-64", python="3.14", qgis="4.2", qt="6.11", chromium="140"
)


def test_the_matrix_is_explicit_about_every_cell() -> None:
    assert SUPPORT_MATRIX, "the kit must state where it runs"
    seen = set()
    for target in SUPPORT_MATRIX:
        key = (target.os, target.arch, target.python, target.qgis)
        assert key not in seen, f"{key} is stated twice"
        seen.add(key)
        assert target.os in {"linux", "windows", "macos"}
        assert target.arch in {"x86-64", "arm64"}
        assert re.fullmatch(r"3\.\d+", target.python)
        assert target.qgis is None or re.fullmatch(r"[34]\.\d+", target.qgis)
        assert target.status in {"qualified", "unqualified"}
        assert target.evidence.strip(), f"{key} states no evidence"
        if target.qgis is None:
            assert target.qt is None and target.chromium is None
        if target.status == "qualified" and target.qgis is not None:
            assert target.qt, f"{key} is qualified without naming its Qt"
            # A row states its Chromium when it exercised the WebEngine layer.
            # The LTS row does not, and says so in its evidence, so it leaves
            # the cell empty instead of inventing a version.
            if target.chromium is None:
                assert "WebEngine" in target.evidence, (
                    f"{key} claims a QGIS without naming its Chromium or why "
                    "the WebEngine layer is absent"
                )


def test_the_matrix_states_the_lts_row_beside_the_locked_environment() -> None:
    lts = qualified_target(
        Host(
            os="linux",
            arch="x86-64",
            python="3.12",
            qgis="3.44",
            qt="5.15",
            chromium=None,
        )
    )

    assert lts is not None
    assert lts.status == "qualified"
    assert lts.chromium is None
    assert "QGIS 3.44 LTS" in lts.evidence


def test_the_matrix_states_the_demonstrated_linux_host() -> None:
    target = qualified_target(LINUX)

    assert target is not None
    assert target.status == "qualified"
    assert (target.qt, target.chromium) == ("6.11", "140")


def test_the_matrix_declares_the_python_floor_and_the_pip_only_platforms() -> None:
    def rows(**attributes: object) -> list[Target]:
        return [
            target
            for target in SUPPORT_MATRIX
            if all(getattr(target, key) == value for key, value in attributes.items())
        ]

    assert rows(python="3.11", qgis=None, status="qualified")
    assert rows(os="windows", qgis=None, status="qualified")
    assert rows(os="macos", qgis=None, status="qualified")
    assert rows(os="windows", status="unqualified")
    assert rows(os="macos", status="unqualified")


def test_a_host_matches_on_os_arch_python_and_qgis_series() -> None:
    assert qualified_target(LINUX._replace(qgis="4.3")) is None
    assert qualified_target(LINUX._replace(python="3.13")) is None
    assert qualified_target(LINUX._replace(arch="arm64")) is None
    qgis_free = qualified_target(LINUX._replace(qgis=None, qt=None, chromium=None))
    assert qgis_free is not None and qgis_free.qgis == "4.2", (
        "without QGIS a host is covered by the row that qualified the same "
        "interpreter with QGIS: the QGIS-free suite is part of it"
    )
    windows = qualified_target(Host("windows", "x86-64", "3.14", None, None, None))
    assert windows is not None and windows.status == "qualified"
    windows_qgis = qualified_target(
        Host("windows", "x86-64", "3.14", "4.2", "6.11", "140")
    )
    assert windows_qgis is not None and windows_qgis.status == "unqualified"


def test_a_qualified_row_names_the_qt_and_chromium_it_was_seen_with() -> None:
    assert qualified_target(LINUX._replace(qt="6.12")) is None
    assert qualified_target(LINUX._replace(chromium="141")) is None


def test_version_prefix_keeps_the_series_and_drops_the_rest() -> None:
    assert version_prefix("4.2.3-Belém do Pará", 2) == "4.2"
    assert version_prefix("6.11.2", 2) == "6.11"
    assert version_prefix("140.0.7339.225", 1) == "140"
    assert version_prefix("", 2) is None
    assert version_prefix(None, 2) is None


def test_describe_host_reads_the_interpreter_and_the_probes(monkeypatch) -> None:
    monkeypatch.setattr(targets_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(targets_module.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(targets_module.platform, "python_version", lambda: "3.14.2")
    versions = {"qgis": "4.2.3-Belém", "qt": "6.11.2", "chromium": "140.0.7339.225"}

    host = describe_host(probe=versions.get)

    assert host == Host("windows", "x86-64", "3.14", "4.2", "6.11", "140")


def test_describe_host_reports_a_qgis_free_interpreter(monkeypatch) -> None:
    monkeypatch.setattr(targets_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(targets_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(targets_module.platform, "python_version", lambda: "3.14.0")

    host = describe_host(probe=lambda name: None)

    assert host == Host("macos", "arm64", "3.14", None, None, None)


def test_the_default_probe_answers_none_where_the_bindings_are_missing(
    monkeypatch,
) -> None:
    def refuse(name: str):
        raise ImportError(name)

    monkeypatch.setattr(targets_module.importlib, "import_module", refuse)

    assert targets_module.probe_installed("qgis") is None
    assert targets_module.probe_installed("qt") is None
    assert targets_module.probe_installed("chromium") is None
    assert targets_module.probe_installed("gdal") is None


def test_the_default_probe_reads_the_first_binding_that_imports(monkeypatch) -> None:
    class QtCore:
        QT_VERSION_STR = "6.11.2"

    class WebEngineCore:
        @staticmethod
        def qWebEngineChromiumVersion() -> str:
            return "140.0.7339.225"

    modules = {"PyQt6.QtCore": QtCore, "PyQt6.QtWebEngineCore": WebEngineCore}

    def import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr(targets_module.importlib, "import_module", import_module)

    assert targets_module.probe_installed("qt") == "6.11.2"
    assert targets_module.probe_installed("chromium") == "140.0.7339.225"
    assert targets_module.probe_installed("qgis") is None


def test_probe_installed_imports_from_the_bindings_it_is_given(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(targets_module.sys, "path", list(targets_module.sys.path))
    bindings = tmp_path / "share" / "qgis" / "python"
    bindings.mkdir(parents=True)

    probe = targets_module.bindings_probe(bindings)
    probe("qgis")

    assert targets_module.sys.path[-1] == str(bindings)
    probe("qt")
    assert targets_module.sys.path.count(str(bindings)) == 1


def test_render_markdown_is_a_table_with_one_row_per_target() -> None:
    table = render_markdown(SUPPORT_MATRIX)

    lines = table.splitlines()
    assert lines[0].startswith("| OS | Arch | Python | QGIS | Qt | Chromium | Status |")
    assert lines[1].startswith("| :-- |")
    assert len(lines) == 2 + len(SUPPORT_MATRIX)
    assert "| linux | x86-64 | 3.14 | 4.2 | 6.11 | 140 | qualified |" in table
    assert "| windows | x86-64 | 3.14 | - | - | - | qualified |" in table


def test_the_python_guide_renders_the_same_matrix() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    begin, end = "<!-- support-matrix:begin -->", "<!-- support-matrix:end -->"
    assert begin in text and end in text, "doc-12 must carry the rendered matrix"
    rendered = text.split(begin, 1)[1].split(end, 1)[0].strip()

    assert rendered == render_markdown(SUPPORT_MATRIX), (
        "doc-12's table drifted from qgis_sdk_tools.targets; "
        "paste `qgis-sdk targets` between the markers"
    )


def test_targets_prints_the_matrix_and_names_the_host(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(targets_module, "describe_host", lambda **_: LINUX)
    runtime = FakeCliRuntime(tmp_path)

    result = CliRunner().invoke(app, ["targets"], obj=runtime)

    assert result.exit_code == 0, result.output
    out = runtime.out.getvalue()
    assert render_markdown(SUPPORT_MATRIX) in out
    assert (
        "this host: linux x86-64, Python 3.14, QGIS 4.2, Qt 6.11, Chromium 140" in out
    )
    assert "qualified" in out.rsplit("this host:", 1)[1]


def test_targets_json_carries_the_rows_and_the_verdict(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        targets_module, "describe_host", lambda **_: LINUX._replace(qgis="4.3")
    )
    runtime = FakeCliRuntime(tmp_path)

    result = CliRunner().invoke(app, ["targets", "--json"], obj=runtime)

    assert result.exit_code == 0, result.output
    payload = json.loads(runtime.out.getvalue())
    assert payload["host"] == {
        "os": "linux",
        "arch": "x86-64",
        "python": "3.14",
        "qgis": "4.3",
        "qt": "6.11",
        "chromium": "140",
    }
    assert payload["status"] == "unqualified"
    assert payload["target"] is None
    assert [row["python"] for row in payload["targets"]] == [
        target.python for target in SUPPORT_MATRIX
    ]
    assert payload["targets"][0]["evidence"]


def test_targets_does_not_fail_an_unqualified_host(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        targets_module, "describe_host", lambda **_: LINUX._replace(qgis="4.3")
    )
    runtime = FakeCliRuntime(tmp_path)

    result = CliRunner().invoke(app, ["targets"], obj=runtime)

    assert result.exit_code == 0
    assert "unqualified" in runtime.out.getvalue()


def test_targets_describes_the_qgis_install_the_other_commands_find(
    monkeypatch, tmp_path
) -> None:
    from qgis_sdk_tools._commands import _targets as targets_command

    asked: dict[str, object] = {}

    class Install:
        bindings = tmp_path / "bindings"

    def find(env, *, prefix=None, project=None):
        asked.update(prefix=prefix, project=project)
        return Install()

    versions = {"qgis": "4.2.3-Belém", "qt": "6.11.2", "chromium": "140.0.1.2"}
    monkeypatch.setattr(targets_command, "find_qgis_install", find)
    monkeypatch.setattr(targets_module, "bindings_probe", lambda bindings: versions.get)
    monkeypatch.setattr(targets_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(targets_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(targets_module.platform, "python_version", lambda: "3.14.8")
    runtime = FakeCliRuntime(tmp_path)

    result = CliRunner().invoke(
        app, ["targets", "--json", "--qgis-prefix", "/opt/qgis"], obj=runtime
    )

    assert result.exit_code == 0, result.output
    assert asked == {"prefix": Path("/opt/qgis"), "project": tmp_path}
    payload = json.loads(runtime.out.getvalue())
    assert payload["host"]["qgis"] == "4.2"
    assert payload["status"] == "qualified"


def test_targets_falls_back_to_the_interpreter_without_a_qgis_install(
    monkeypatch, tmp_path
) -> None:
    from qgis_sdk_tools._commands import _targets as targets_command
    from qgis_sdk_tools.devtools import QgisSdkQgisNotFoundError

    def missing(env, *, prefix=None, project=None):
        raise QgisSdkQgisNotFoundError("no QGIS")

    monkeypatch.setattr(targets_command, "find_qgis_install", missing)
    monkeypatch.setattr(targets_module, "probe_installed", lambda name: None)
    runtime = FakeCliRuntime(tmp_path)

    result = CliRunner().invoke(app, ["targets", "--json"], obj=runtime)

    assert result.exit_code == 0, result.output
    assert json.loads(runtime.out.getvalue())["host"]["qgis"] is None
