"""Put the developer scripts and the test-only fixtures on the import path, and
declare the test layers.

The package suite runs from the package directory locally and from the repository
root in CI, and the repository root owns its own top-level ``scripts`` package, so
the module roots are added here by absolute path instead of importing through a
package name that would collide.

The layers - ``pure``, ``qt``, ``qgis``, ``webengine``, ``desktop`` and the
``native`` umbrella - are documented in :mod:`layers`. This file registers the
markers, derives ``pure``/``native`` from the explicit ones, prepares the
headless environment before any native module is collected, and owns the one
application fixture every native module shares.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

for _path in (PROJECT_ROOT / "tests", PROJECT_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import layers

layers.prepare_environment()

# Step definitions and fixtures shared between the BDD features and the
# ordinary tests; declared here so every module sees the same ones.
pytest_plugins = ["bridge_steps"]


def pytest_configure(config: pytest.Config) -> None:
    for name, help_text in layers.LAYER_HELP.items():
        config.addinivalue_line("markers", f"{name}: {help_text}")


SCAFFOLD_WEB_MODULE = "test_scaffold_web_native.py"
"""The one webengine module that drives a *generated* plugin's view.

That view uses Chromium's default profile, while every other webengine module
shares the off-the-record ``webengine_profile`` below. Chromium aborts the
process (exit 134, after the tests passed) when a page on the shared profile is
created after the default profile's pages were torn down, so the two cannot
share a process: doc-14 runs each opt-in harness file on its own.
"""


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Derive ``native`` and ``pure`` so each half of the suite is one ``-m``.

    And keep the scaffold-web harness alone with Chromium: when it is collected
    (``QGIS_SDK_SCAFFOLD_WEB`` set) every webengine test of another module is
    skipped, with the reason, instead of taking the whole process down.
    """
    scaffold_web_live = any(item.path.name == SCAFFOLD_WEB_MODULE for item in items)
    for item in items:
        declared = {marker.name for marker in item.iter_markers()}
        if declared & layers.NATIVE_LAYERS:
            item.add_marker(pytest.mark.native)
        else:
            item.add_marker(pytest.mark.pure)
        if (
            scaffold_web_live
            and "webengine" in declared
            and item.path.name != SCAFFOLD_WEB_MODULE
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason=f"{SCAFFOLD_WEB_MODULE} owns Chromium in this process; "
                    "run the webengine modules in a separate process (doc-14)"
                )
            )


@pytest.fixture(scope="session")
def qt_app() -> Any:
    """The one Qt application of this test process; skips when there is no Qt.

    A ``QgsApplication`` whenever the QGIS bindings are importable, so the
    ``qt`` and ``qgis`` layers never disagree about which application a process
    holds (see :mod:`layers`).
    """
    try:
        return layers.start_application()
    except ImportError as error:  # pragma: no cover - depends on the host
        pytest.skip(f"the qt layer needs Qt: {error}")


@pytest.fixture(scope="session")
def qgis_app(qt_app: Any) -> Any:
    """The application, with QGIS initialised; skips when only Qt is present."""
    if not layers.is_qgis_application(qt_app):  # pragma: no cover - host-dependent
        pytest.skip("the qgis layer needs the qgis Python bindings")
    return qt_app


@pytest.fixture(scope="session")
def webengine_profile(qt_app: Any) -> Any:
    """The one off-the-record ``QWebEngineProfile`` of the process.

    Chromium tears a profile down once: a second profile created after the
    first was destroyed - or two left alive at exit - aborts the process after
    the last test passed. So every webengine module shares this one, and the
    pages come and go underneath it.
    """
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile
    except ImportError as error:  # pragma: no cover - depends on the host
        pytest.skip(f"the webengine layer needs Qt WebEngine: {error}")
    return QWebEngineProfile(qt_app)


@pytest.fixture(scope="session", autouse=True)
def _stop_the_application_after_the_session() -> Iterator[None]:
    """Exit QGIS exactly once, after the last test, if this session started it."""
    yield
    layers.stop_application()
