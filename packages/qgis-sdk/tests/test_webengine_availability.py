"""Characterize optional Qt WebEngine availability without requiring QGIS."""

from __future__ import annotations

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
        import sys
        import importlib

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


def test_create_webengine_view_raises_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webengine, "_import_webengine_view", lambda: None)
    with pytest.raises(QgisSdkOptionalDependencyError) as exc_info:
        webengine.create_webengine_view()
    assert exc_info.value.dependency == "pyqt6-webengine"


def test_availability_is_false_when_the_bindings_cannot_be_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in (
        "qgis.PyQt.QtWebEngineWidgets",
        "PyQt6.QtWebEngineWidgets",
        "PyQt5.QtWebEngineWidgets",
    ):
        monkeypatch.setitem(sys.modules, module_name, None)

    assert webengine.webengine_available() is False


def test_require_webengine_raises_an_actionable_error_without_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in (
        "qgis.PyQt.QtWebEngineWidgets",
        "PyQt6.QtWebEngineWidgets",
        "PyQt5.QtWebEngineWidgets",
    ):
        monkeypatch.setitem(sys.modules, module_name, None)

    with pytest.raises(QgisSdkOptionalDependencyError) as exc_info:
        webengine.require_webengine()
    assert exc_info.value.dependency == "pyqt6-webengine"
    assert "pyqt6-webengine" in exc_info.value.installation_hint


def test_create_webengine_view_uses_resolved_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeView:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr(webengine, "_import_webengine_view", lambda: FakeView)
    view = webengine.create_webengine_view(1, value=2)
    assert isinstance(view, FakeView)
    assert view.args == (1,)
    assert view.kwargs == {"value": 2}


def test_create_restricted_page_raises_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webengine, "_import_webengine_core", lambda: None)
    with pytest.raises(QgisSdkOptionalDependencyError) as exc_info:
        webengine.create_restricted_page(webengine.BrowserPolicy())
    assert exc_info.value.dependency == "pyqt6-webengine"


def test_the_core_import_is_none_when_the_bindings_cannot_be_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in (
        "qgis.PyQt.QtWebEngineCore",
        "PyQt6.QtWebEngineCore",
        "PyQt5.QtWebEngineWidgets",
        "PyQt5.QtWebEngineCore",
    ):
        monkeypatch.setitem(sys.modules, module_name, None)
    assert webengine._import_webengine_core() is None
