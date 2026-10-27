"""QGIS001 and ARCH001: native imports that run when a module loads (TASK-16)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from qgis_sdk_tools.check import Diagnostic, check_source

MODULE = Path("field_tools/plugin.py")


def diagnostics(source: str, *, path: Path = MODULE, **kwargs) -> list[Diagnostic]:
    return list(check_source(textwrap.dedent(source), path=path, **kwargs))


def rules(source: str, **kwargs) -> list[tuple[str, int]]:
    return [(d.rule, d.line) for d in diagnostics(source, **kwargs)]


@pytest.mark.parametrize(
    "statement",
    [
        "import qgis",
        "import qgis.core",
        "from qgis.core import QgsProject",
        "from qgis.PyQt.QtWidgets import QDialog",
        "import PyQt5.QtCore",
        "from PyQt6 import QtWidgets",
        "from PySide6.QtCore import QObject",
        "import qgis.core as core, os",
    ],
)
def test_a_native_import_at_module_scope_is_qgis001(statement: str) -> None:
    assert rules(f"import os\n{statement}\n") == [("QGIS001", 2)]


@pytest.mark.parametrize(
    "source",
    [
        # class body runs at import time
        """
        class Plugin:
            from qgis.core import QgsProject
        """,
        # try/except does not make an import lazy, only optional
        """
        try:
            from qgis.core import QgsProject
        except ImportError:
            QgsProject = None
        """,
        # a module-level condition still runs when the module loads
        """
        import sys
        if sys.platform == "win32":
            import qgis.core
        """,
        # the else branch of a TYPE_CHECKING guard is live code
        """
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            pass
        else:
            from qgis.core import QgsProject
        """,
        # with / for / while blocks at module scope
        """
        import contextlib
        with contextlib.suppress(ImportError):
            import qgis.gui
        """,
    ],
)
def test_a_native_import_inside_a_module_scope_block_is_still_import_time(
    source: str,
) -> None:
    found = rules(source)
    assert [rule for rule, _ in found] == ["QGIS001"], found


@pytest.mark.parametrize(
    "source",
    [
        """
        def open_dialog():
            from qgis.PyQt.QtWidgets import QDialog
            return QDialog()
        """,
        """
        class Plugin:
            def run(self):
                import qgis.core
        """,
        """
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from qgis.core import QgsProject
        """,
        """
        import typing
        if typing.TYPE_CHECKING:
            from qgis.gui import QgisInterface
        """,
        """
        import typing as t
        if t.TYPE_CHECKING:
            from qgis.gui import QgisInterface
        """,
        """
        async def fetch():
            from qgis.core import QgsNetworkAccessManager
        """,
        # a lambda body is deferred too (no import statement fits, but a call
        # expression that imports does): importlib is not a native root
        """
        import importlib
        load = lambda: importlib.import_module("os")
        """,
    ],
)
def test_a_deferred_or_type_checking_import_is_allowed(source: str) -> None:
    assert rules(source) == []


def test_the_diagnostic_names_the_module_the_line_the_column_and_a_remedy() -> None:
    (found,) = diagnostics("import os\n\nfrom qgis.core import QgsProject\n")

    assert found.rule == "QGIS001"
    assert found.path == MODULE
    assert (found.line, found.column) == (3, 1)
    assert found.severity == "error"
    assert "qgis.core" in found.message
    assert "loads" in found.message
    assert "TYPE_CHECKING" in found.remediation
    assert "native-modules" in found.remediation
    assert found.render() == (
        "field_tools/plugin.py:3:1: QGIS001 "
        + found.message
        + "\n    "
        + found.remediation
    )


def test_one_diagnostic_per_offending_statement_in_source_order() -> None:
    source = """
    import qgis.core
    from PyQt5 import QtCore
    import os
    class A:
        import qgis.gui
    """
    assert rules(source) == [("QGIS001", 2), ("QGIS001", 3), ("QGIS001", 6)]


def test_a_module_declared_native_may_import_qgis_when_it_loads() -> None:
    source = "from qgis.core import QgsProject\n"
    native = Path("field_tools/native/views.py")

    assert rules(source, path=native, native_modules=("field_tools.native.*",)) == []
    assert rules(source, path=native, native_modules=("field_tools.native",)) == [
        ("QGIS001", 1)
    ]
    assert (
        rules(
            source,
            path=Path("field_tools/native/__init__.py"),
            native_modules=("field_tools.native",),
        )
        == []
    )


def test_the_sdks_native_adapter_package_is_arch001_from_a_pure_module() -> None:
    source = """
    from qgis_sdk.adapters.desktop import create_class_factory
    from qgis_sdk.adapters.qgis import native_plugin_context
    import qgis_sdk.adapters.qgis.context
    """
    found = diagnostics(source)

    assert [(d.rule, d.line) for d in found] == [("ARCH001", 3), ("ARCH001", 4)]
    assert "qgis_sdk.adapters.qgis" in found[0].message
    assert "native-modules" in found[0].remediation


def test_arch001_is_lifted_inside_a_declared_native_module() -> None:
    source = "from qgis_sdk.adapters.qgis import native_plugin_context\n"
    assert (
        rules(
            source,
            path=Path("field_tools/native.py"),
            native_modules=("field_tools.native",),
        )
        == []
    )


def test_a_syntax_error_is_reported_as_a_diagnostic_not_an_exception() -> None:
    (found,) = diagnostics("def broken(:\n    pass\n")

    assert found.rule == "SYNTAX001"
    assert found.line == 1
    assert found.severity == "error"


def test_qt_at_module_level_in_a_declared_native_module_is_a_ui004_warning() -> None:
    source = """
        from qgis.core import QgsProject
        from qgis.PyQt.QtWidgets import QDialog
        import PyQt5.QtCore
        from qgis.PyQt import uic

        def later():
            from qgis.PyQt.QtWidgets import QLabel
        """
    native = Path("field_tools/native/views.py")
    found = diagnostics(source, path=native, native_modules=("field_tools.native.*",))

    assert [(d.rule, d.line, d.severity) for d in found] == [
        ("UI004", 3, "warning"),
        ("UI004", 4, "warning"),
        ("UI004", 5, "warning"),
    ]
    assert "defeats the fakes" in found[0].message
    assert "build()" in found[0].remediation
    # Outside the plugin package (a test module) the rule stays quiet.
    assert (
        diagnostics(
            source, path=Path("tests/test_views.py"), native_modules=("tests.*",)
        )
        == []
    )
