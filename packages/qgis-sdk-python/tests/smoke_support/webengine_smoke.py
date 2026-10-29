"""Repeatable headless QGIS and Qt WebEngine qualification harness.

This is the test-support half of the TASK-23 headless qualification. It records
the environment a headless WebEngine run needs, loads a page in a real
``QWebEngineView`` hosted by a real QGIS application, and prints a
machine-readable report describing what actually ran.

Run its pytest smoke test with ``pytest -m smoke``.

The module is importable without Qt or QGIS: the environment and report
helpers are pure, so the QGIS-free suite can test them, while the optional
smoke test runs the helper in an isolated subprocess.

Platform prerequisites are recorded in ``packages/qgis-sdk-python/README.md``.
"""

from __future__ import annotations

import os
import platform
import re
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path

HEADLESS_PLATFORM = "offscreen"
CHROMIUM_FLAGS = "--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process"
LOAD_TIMEOUT_MS = 30_000
SMOKE_HTML = "<html><body><h1>QGIS SDK WebEngine qualification</h1></body></html>"


def qgis_python_path(prefix: Path) -> Path:
    """Return the directory holding the QGIS Python bindings of a prefix."""
    return prefix / "share" / "qgis" / "python"


def headless_environment(prefix: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """Return the environment overrides a headless QGIS/WebEngine run needs.

    ``PYTHONPATH`` keeps any entry the caller already had, so the harness can
    run inside a workspace that puts the SDK sources on the path.
    """
    python_path = [str(qgis_python_path(prefix))]
    existing = environ.get("PYTHONPATH")
    if existing:
        python_path.append(existing)
    return {
        "QT_QPA_PLATFORM": HEADLESS_PLATFORM,
        "QTWEBENGINE_CHROMIUM_FLAGS": CHROMIUM_FLAGS,
        "PROJ_LIB": str(prefix / "share" / "proj"),
        "QGIS_PREFIX_PATH": str(prefix),
        "PYTHONPATH": os.pathsep.join(python_path),
    }


def chromium_version(user_agent: str) -> str | None:
    """Return the Chromium version advertised by a Qt WebEngine user agent."""
    match = re.search(r"Chrome/(\d+(?:\.\d+)*)", user_agent)
    return match.group(1) if match else None


@dataclass(frozen=True)
class QualificationReport:
    """What a headless qualification run observed."""

    platform: str
    python_version: str
    qgis_version: str | None
    qt_version: str | None
    chromium_version: str | None
    webengine_available: bool
    qgis_initialised: bool
    load_finished: bool
    qgis_exited: bool
    error: str | None = None

    @property
    def qualified(self) -> bool:
        """Return whether every stage of the headless run succeeded."""
        return (
            self.webengine_available
            and self.qgis_initialised
            and self.load_finished
            and self.qgis_exited
        )

    @classmethod
    def unavailable(cls, error: str | None = None) -> QualificationReport:
        """Return the report for a host that cannot offer QGIS or WebEngine.

        Every stage is false and no version is known: the harness answers with this
        instead of raising, so a broken environment still produces a machine-readable
        report - and one place decides what "did not get that far" looks like.
        """
        return cls(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            qt_version=None,
            chromium_version=None,
            webengine_available=False,
            qgis_initialised=False,
            load_finished=False,
            qgis_exited=False,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable mapping."""
        payload = asdict(self)
        payload["qualified"] = self.qualified
        return payload


def run_smoke(
    prefix: Path | None = None, timeout_ms: int = LOAD_TIMEOUT_MS
) -> QualificationReport:
    """Run a headless QGIS + WebEngine load and report what happened.

    The process is prepared for a headless run before any native module is
    imported: the Qt platform, Chromium flags, PROJ data and the QGIS Python
    path are all resolved from ``prefix``.
    """
    prefix = prefix or Path(sys.prefix)
    for key, value in headless_environment(prefix, os.environ).items():
        os.environ[key] = value
    sys.path.insert(0, str(qgis_python_path(prefix)))

    report = QualificationReport.unavailable()
    try:
        report = _run_headless_load(prefix, timeout_ms)
    except Exception as error:  # noqa: BLE001 - report a broken environment as a failure
        # The report records any failure instead of raising, so a broken
        # environment still produces machine-readable output.
        report = replace(report, error=f"{type(error).__name__}: {error}")
    return report


def _run_headless_load(prefix: Path, timeout_ms: int) -> QualificationReport:
    """Start QGIS, load a page in a WebEngine view and tear QGIS down."""
    from PyQt6.QtCore import QT_VERSION_STR, Qt, QTimer
    from PyQt6.QtWidgets import QApplication

    # WebEngine shares its OpenGL context, so the attribute has to be set
    # before the application object exists.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    from qgis.core import Qgis, QgsApplication

    QgsApplication.setPrefixPath(str(prefix), True)
    application = QgsApplication([b"qgis-webengine-smoke"], True)
    application.initQgis()

    from PyQt6.QtWebEngineCore import QWebEngineProfile
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    user_agent = QWebEngineProfile().httpUserAgent()
    view = QWebEngineView()
    view.setHtml(SMOKE_HTML)

    finished: list[bool] = []

    def on_load_finished(ok: bool) -> None:
        finished.append(ok)
        application.quit()

    view.loadFinished.connect(on_load_finished)
    # The timer only bounds the wait when the page never finishes loading.
    QTimer.singleShot(timeout_ms, application.quit)
    application.exec()

    application.exitQgis()
    return QualificationReport(
        platform=platform.platform(),
        python_version=platform.python_version(),
        qgis_version=Qgis.QGIS_VERSION,
        qt_version=QT_VERSION_STR,
        chromium_version=chromium_version(user_agent),
        webengine_available=True,
        qgis_initialised=True,
        load_finished=bool(finished) and finished[-1],
        qgis_exited=True,
    )
