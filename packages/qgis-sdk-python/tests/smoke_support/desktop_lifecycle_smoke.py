"""Repeatable headless QGIS plugin lifecycle harness.

This helper starts a real QGIS application, runs the SDK's Desktop lifecycle
adapter through ``initGui`` and repeated ``unload``, and prints a
machine-readable report. It is **not** a Desktop GUI qualification: there is no
display, no real ``iface`` and no menu/dock integration in this sandbox. The
real Desktop path remains tracked separately.

Run its pytest smoke test with ``pytest -m smoke``.

The report helpers are pure, so the QGIS-free suite can test them; the
end-to-end run is opt-in through the test suite.
"""

from __future__ import annotations

import os
import platform
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_run_lifecycle_p1(_s):
    from PyQt6.QtCore import QT_VERSION_STR

    _s.QT_VERSION_STR = QT_VERSION_STR
    from qgis.core import Qgis, QgsApplication

    _s.Qgis = Qgis
    _s.QgsApplication = QgsApplication

    _s.QgsApplication.setPrefixPath(str(_s.prefix), True)
    _s.application = _s.QgsApplication([b"qgis-sdk-lifecycle-smoke"], True)
    _s.application.initQgis()

    from qgis_sdk import QgisSdkPlugin

    _s.QgisSdkPlugin = QgisSdkPlugin
    from qgis_sdk.adapters.desktop import DesktopLifecycleAdapter

    _s.DesktopLifecycleAdapter = DesktopLifecycleAdapter
    from qgis_sdk.core import ResourceScope

    _s.ResourceScope = ResourceScope

    _s.released: list[str] = []


def _cc_run_lifecycle_p2(_s):

    class Notifications:
        def info(self, message: str) -> None:
            del message

        _s.info = info

    _s.Notifications = Notifications

    _s.app = _s.QgisSdkPlugin(
        id="qualification.lifecycle", title="Lifecycle qualification"
    )

    @_s.app.action(id="ping", title="Ping")
    def ping(ctx: PluginContext, value: int) -> int:
        return value

    _s.ping = ping


def _cc_run_lifecycle_p3(_s):

    def context_factory(iface: object) -> PluginContext:
        del iface  # a real Desktop iface is not available in this harness
        scope = _s.ResourceScope()
        for name in ("action", "signal", "dock", "work"):
            _s.name = name
            scope.on_close(lambda name=name: _s.released.append(name))
        return PluginContext(_s.Notifications(), scope)

    _s.context_factory = context_factory

    _s.qgis_initialised = True


def _cc_run_lifecycle_p4(_s):
    try:
        _s.adapter = _s.DesktopLifecycleAdapter(
            _s.app, iface=None, context_factory=_s.context_factory
        )
        _s.adapter.initGui()
        _s.plugin_started = _s.adapter.runtime.state.value == "running"
        _s.action_names = tuple(sorted(_s.adapter.runtime.actions))
        _s.action_result = _s.adapter.runtime.actions["ping"](PING_VALUE)
        _s.adapter.unload()
        _s.adapter.unload()
        _s.plugin_unloaded = _s.adapter.runtime.state.value == "stopped"
        _s.owned_resources_released = _s.released == [
            "work",
            "dock",
            "signal",
            "action",
        ]
    finally:
        _s.application.exitQgis()


def _cc_run_lifecycle_p5(_s):

    return _CcReturn(
        LifecycleReport(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=_s.Qgis.QGIS_VERSION,
            qt_version=_s.QT_VERSION_STR,
            qgis_initialised=_s.qgis_initialised,
            plugin_started=_s.plugin_started,
            action_names=_s.action_names,
            action_result=_s.action_result,
            plugin_unloaded=_s.plugin_unloaded,
            owned_resources_released=_s.owned_resources_released,
            qgis_exited=True,
        )
    )


HEADLESS_PLATFORM = "offscreen"
PING_VALUE = 7
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The runtime and the tools are separate distributions (decision-35); both go
# on the path so the probe imports the trees under test.
SOURCE_ROOTS = (
    PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src",
    PROJECT_ROOT.parent / "qgis-sdk-tools" / "src",
)
# Handler annotations are resolved from module globals. Keep this import pure,
# and make the source tree available to the isolated test process.
for _root in reversed(SOURCE_ROOTS):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from qgis_sdk.core import PluginContext


def qgis_python_path(prefix: Path) -> Path:
    """Return the directory holding the QGIS Python bindings of a prefix."""
    return prefix / "share" / "qgis" / "python"


def headless_environment(prefix: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """Return the overrides a headless QGIS lifecycle run needs."""
    python_path = [str(qgis_python_path(prefix))]
    existing = environ.get("PYTHONPATH")
    if existing:
        python_path.append(existing)
    return {
        "QT_QPA_PLATFORM": HEADLESS_PLATFORM,
        "PROJ_LIB": str(prefix / "share" / "proj"),
        "QGIS_PREFIX_PATH": str(prefix),
        "PYTHONPATH": os.pathsep.join(python_path),
    }


@dataclass(frozen=True)
class LifecycleReport:
    """What a headless plugin lifecycle run observed."""

    platform: str
    python_version: str
    qgis_version: str | None
    qt_version: str | None
    qgis_initialised: bool
    plugin_started: bool
    action_names: tuple[str, ...]
    action_result: int | None
    plugin_unloaded: bool
    owned_resources_released: bool
    qgis_exited: bool
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether every headless lifecycle stage succeeded."""
        return all(
            (
                self.qgis_initialised,
                self.plugin_started,
                self.action_result == PING_VALUE,
                self.plugin_unloaded,
                self.owned_resources_released,
                self.qgis_exited,
            )
        )

    @classmethod
    def unavailable(cls, error: str | None = None) -> LifecycleReport:
        """Return the report for a host where nothing could run.

        Every stage is false and no version is known. The harness answers with this
        instead of raising, so a broken environment still produces a machine-readable
        report - and one place decides what "did not get that far" looks like.
        """
        return cls(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            qt_version=None,
            qgis_initialised=False,
            plugin_started=False,
            action_names=(),
            action_result=None,
            plugin_unloaded=False,
            owned_resources_released=False,
            qgis_exited=False,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable mapping."""
        payload = asdict(self)
        payload["action_names"] = list(self.action_names)
        payload["passed"] = self.passed
        return payload


def run_smoke(prefix: Path | None = None) -> LifecycleReport:
    """Start QGIS, run the lifecycle adapter and report what happened."""
    prefix = prefix or Path(sys.prefix)
    for key, value in headless_environment(prefix, os.environ).items():
        os.environ[key] = value
    sys.path.insert(0, str(qgis_python_path(prefix)))
    for root in reversed(SOURCE_ROOTS):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

    failed = LifecycleReport.unavailable()
    try:
        return _run_lifecycle(prefix)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return replace(failed, error=f"{type(error).__name__}: {error}")


def _run_lifecycle(prefix: Path) -> LifecycleReport:
    """Run one plugin lifecycle inside a real headless QgsApplication."""
    _s = _CcState(prefix=prefix)
    for _p in (
        _cc_run_lifecycle_p1,
        _cc_run_lifecycle_p2,
        _cc_run_lifecycle_p3,
        _cc_run_lifecycle_p4,
        _cc_run_lifecycle_p5,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
