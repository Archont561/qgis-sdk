"""``qgis_sdk_tools.manifest`` is the one reading of ``pyproject.toml``.

Every command that opens the manifest - ``check``, ``build``, ``dev`` and the
project loader - goes through ``read_pyproject`` and ``table``; the three
outcomes a reader distinguishes (parsed, absent, malformed) are pinned here so
the callers can keep their own policies on top of one shared reading.
"""

from __future__ import annotations

from pathlib import Path

from qgis_sdk_tools.manifest import read_pyproject, table


def test_a_manifest_that_parses_comes_back_as_its_tables(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.qgis-sdk]\nplugin = "p.m:C"\n', encoding="utf-8")

    data, malformed = read_pyproject(path)

    assert malformed is None
    assert table(data, "tool", "qgis-sdk") == {"plugin": "p.m:C"}


def test_an_absent_manifest_is_neither_data_nor_a_parse_failure(tmp_path: Path) -> None:
    assert read_pyproject(tmp_path / "pyproject.toml") == (None, None)


def test_a_malformed_manifest_quotes_the_parser(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.qgis-sdk\n", encoding="utf-8")

    data, malformed = read_pyproject(path)

    assert data is None
    assert malformed is not None and "line 1" in malformed


def test_table_returns_none_for_any_step_that_is_not_a_table() -> None:
    data = {"tool": {"qgis-sdk": {"build": "not-a-table"}}}

    assert table(data, "tool", "qgis-sdk") == {"build": "not-a-table"}
    assert table(data, "tool", "qgis-sdk", "build") is None
    assert table(data, "tool", "missing") is None
    assert table(None, "tool") is None
    assert table(data) == data
