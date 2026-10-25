"""What the native test layers share: the environment, and one application.

Imported by ``conftest.py`` (so the environment is ready before any native
module is collected) and by the native modules and the services backend (so
there is one way to start Qt or QGIS in a test process, and one place that
stops it). Nothing here imports Qt at module import time: the pure layer loads
this module too and must stay free of native modules.

Layers, as pytest markers:

``qt``
    needs a Qt event loop - a ``QApplication`` and the PyQt bindings;
``qgis``
    needs an initialised QGIS - a ``QgsApplication`` with its providers, and
    the ``qgis`` Python bindings;
``webengine``
    needs Qt WebEngine (a real Chromium) on top of ``qt``;
``desktop``
    the opt-in end-to-end harnesses under ``tests/scripts`` that launch a real
    QGIS Desktop; each is enabled by its own ``QGIS_SDK_*`` flag.

``native`` is added to every test in one of those layers and ``pure`` to every
other test, so ``-m pure`` is the QGIS-free run and ``-m native`` the rest.

One process holds one application. Whenever the QGIS bindings are importable
the application is a ``QgsApplication`` - it *is* a ``QApplication``, so the
``qt`` layer runs on it unchanged - and QGIS is initialised once and exited once
at the end of the session, whichever module asked first. That is what makes the
layers independent of file order: a run of ``test_jobs_native.py`` alone and a
run of the whole suite start the same application.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

PACKAGES_ROOT = Path(__file__).resolve().parents[2]
"""``packages/``: the workspace directory holding every distribution."""
RUNTIME_SOURCE = PACKAGES_ROOT / "qgis-sdk-runtime" / "src"
TOOLS_SOURCE = PACKAGES_ROOT / "qgis-sdk-tools" / "src"
SOURCE_ROOTS = (RUNTIME_SOURCE, TOOLS_SOURCE)
"""The import roots of the two distributions this suite covers (decision-35).

The runtime and the tools are separate distributions with separate ``src``
trees; a child interpreter that should see the SDK from source puts both on
``PYTHONPATH`` - see :func:`source_path`.
"""


def source_path(*extra: Path | str) -> str:
    """``PYTHONPATH`` value: ``extra`` first, then the two source roots."""
    return os.pathsep.join(str(item) for item in (*extra, *SOURCE_ROOTS))


NATIVE_LAYERS = frozenset({"qt", "qgis", "webengine", "desktop"})
LAYER_HELP = {
    "qt": "needs a Qt event loop (a QApplication and the PyQt bindings)",
    "qgis": "needs an initialised QgsApplication and the qgis Python bindings",
    "webengine": "needs Qt WebEngine (a real Chromium) on top of qt",
    "desktop": "opt-in end-to-end harness against a real QGIS Desktop (QGIS_SDK_* flag)",
    "native": "any test in the qt, qgis, webengine or desktop layer (added automatically)",
    "pure": "runs without QGIS, Qt or a display (added automatically)",
}

CHROMIUM_FLAGS = "--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process"
"""The flags the TASK-23 headless harness qualified for an offscreen Chromium."""

_application: Any = None
_owned = False


def qgis_bindings() -> Path | None:
    """Return the directory holding the QGIS Python bindings, if this prefix has one.

    The pixi environment keeps them in ``share/qgis/python`` rather than on
    ``sys.path``; a pip-only environment has no such directory.
    """
    bindings = Path(sys.prefix) / "share" / "qgis" / "python"
    return bindings if bindings.is_dir() else None


def prepare_environment() -> None:
    """Make Qt and QGIS importable and headless, without importing either.

    Idempotent, and a no-op for anything already set: a developer who exports
    their own platform plugin or prefix keeps it.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", CHROMIUM_FLAGS)
    prefix = Path(sys.prefix)
    os.environ.setdefault("QGIS_PREFIX_PATH", str(prefix))
    os.environ.setdefault("PROJ_LIB", str(prefix / "share" / "proj"))
    # QGIS reads this when the application is constructed, so it has to be in
    # place before whichever module starts it: a test that sets a master
    # password must never touch a developer's real authentication database.
    os.environ.setdefault(
        "QGIS_AUTH_DB_DIR_PATH", tempfile.mkdtemp(prefix="qgis-sdk-auth-")
    )
    bindings = qgis_bindings()
    if bindings is not None and str(bindings) not in sys.path:
        sys.path.insert(0, str(bindings))


def qgis_available() -> bool:
    """Whether ``qgis.core`` can be imported here, without importing it yet."""
    import importlib.util

    prepare_environment()
    return importlib.util.find_spec("qgis.core") is not None


def start_application() -> Any:
    """Return the one application of this process, starting it if needed.

    A ``QgsApplication`` when the QGIS bindings are present, else a plain
    ``QApplication``. An application another party already created - a
    harness, an embedding host - is reused and left alone at the end.
    """
    global _application, _owned
    if _application is not None:
        return _application
    prepare_environment()
    from PyQt6.QtWidgets import QApplication

    existing = QApplication.instance()
    if existing is not None:
        _application = existing
        return existing
    if qgis_available():
        from qgis.core import QgsApplication

        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
        application = QgsApplication([b"qgis-sdk-tests"], True)
        application.initQgis()
    else:
        application = QApplication([sys.argv[0]])
    _application = application
    _owned = True
    return application


def is_qgis_application(application: Any) -> bool:
    """Whether ``application`` carries an initialised QGIS, not just Qt."""
    try:
        from qgis.core import QgsApplication
    except ImportError:
        return False
    return isinstance(application, QgsApplication)


def stop_application() -> None:
    """Exit QGIS if this module started it; called once at the end of a session.

    The ``QApplication`` itself is left to the interpreter: Qt tears it down
    once, at exit, and deleting it earlier while a WebEngine profile or a
    thread pool still references it is what makes a run abort after its last
    test passed.
    """
    global _application, _owned
    application, _application = _application, None
    owned, _owned = _owned, False
    if application is None or not owned:
        return
    if is_qgis_application(application):
        application.exitQgis()
