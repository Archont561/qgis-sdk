"""Characterize optional Qt WebEngine availability without requiring QGIS."""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from qgis_sdk.adapters import webengine
from qgis_sdk.models.errors import QgisSdkOptionalDependencyError


def test_webengine_adapter_imports_without_native_modules(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "qgis_sdk"
    script = textwrap.dedent(
        """
        import importlib
        import sys

        sys.path.insert(0, sys.argv[1])

        class RejectNative:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'qgis', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
                    raise AssertionError(f'eager native import: {fullname}')
                return None

        sys.meta_path.insert(0, RejectNative())
        importlib.import_module('qgis_sdk.adapters.webengine')
        print('native-free')
        """
    )
    result = subprocess.run if False else None
    import subprocess

    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(source_root.parent)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "native-free"


def test_webengine_availability_returns_bool() -> None:
    assert isinstance(webengine.webengine_available(), bool)


def test_require_webengine_matches_availability() -> None:
    if webengine.webengine_available():
        webengine.require_webengine()
    else:
        with pytest.raises(QgisSdkOptionalDependencyError) as exc_info:
            webengine.require_webengine()
        assert exc_info.value.dependency == "pyqt6-webengine"


def test_create_webengine_view_matches_availability() -> None:
    if webengine.webengine_available():
        view = webengine.create_webengine_view()
        assert view is not None
    else:
        with pytest.raises(QgisSdkOptionalDependencyError):
            webengine.create_webengine_view()
