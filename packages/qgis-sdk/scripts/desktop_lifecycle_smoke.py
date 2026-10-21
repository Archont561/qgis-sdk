"""Repeatable headless QGIS plugin lifecycle harness.

This script starts a real QGIS application, runs the SDK's Desktop lifecycle
adapter through ``initGui`` and repeated ``unload``, and prints a
machine-readable report. It is **not** a Desktop GUI qualification: there is no
display, no real ``iface`` and no menu/dock integration in this sandbox. The
real Desktop path remains tracked separately.

Run it from the workspace root with the default Pixi environment::

    pixi run -e default python packages/qgis-sdk/scripts/desktop_lifecycle_smoke.py

The report helpers are pure, so the QGIS-free suite can test them; the
end-to-end run is opt-in through the test suite.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path

HEADLESS_PLATFORM = "offscreen"
PING_VALUE = 7
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"


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
        return (
            self.qgis_initialised
            and self.plugin_started
            and self.action_result == PING_VALUE
            and self.plugin_unloaded
            and self.owned_resources_released
            and self.qgis_exited
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
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))

    failed = LifecycleReport.unavailable()
    try:
        return _run_lifecycle(prefix)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return replace(failed, error=f"{type(error).__name__}: {error}")


def _run_lifecycle(prefix: Path) -> LifecycleReport:
    """Run one plugin lifecycle inside a real headless QgsApplication."""
    from PyQt6.QtCore import QT_VERSION_STR
    from qgis.core import Qgis, QgsApplication

    QgsApplication.setPrefixPath(str(prefix), True)
    application = QgsApplication([b"qgis-sdk-lifecycle-smoke"], True)
    application.initQgis()

    from qgis_sdk import action, plugin
    from qgis_sdk.adapters.desktop import DesktopLifecycleAdapter
    from qgis_sdk.core import PluginContext, ResourceScope

    released: list[str] = []

    class Notifications:
        def info(self, message: str) -> None:
            del message

    @plugin(id="qualification.lifecycle", title="Lifecycle qualification")
    class LifecyclePlugin:
        def __init__(self, ctx: PluginContext) -> None:
            self.ctx = ctx
            ctx.scope.on_close(lambda: released.append("action"))
            ctx.scope.on_close(lambda: released.append("signal"))
            ctx.scope.on_close(lambda: released.append("dock"))
            ctx.scope.on_close(lambda: released.append("work"))

        @action(id="ping", title="Ping")
        def ping(self, value: int) -> int:
            return value

    def context_factory(iface: object) -> PluginContext:
        del iface  # a real Desktop iface is not available in this harness
        return PluginContext(notifications=Notifications(), scope=ResourceScope())

    qgis_initialised = True
    try:
        adapter = DesktopLifecycleAdapter(
            LifecyclePlugin, iface=None, context_factory=context_factory
        )
        adapter.initGui()
        plugin_started = adapter.runtime.state.value == "running"
        action_names = tuple(sorted(adapter.runtime.actions))
        action_result = adapter.runtime.actions["ping"](PING_VALUE)
        adapter.unload()
        adapter.unload()
        plugin_unloaded = adapter.runtime.state.value == "stopped"
        owned_resources_released = released == ["work", "dock", "signal", "action"]
    finally:
        application.exitQgis()

    return LifecycleReport(
        platform=platform.platform(),
        python_version=platform.python_version(),
        qgis_version=Qgis.QGIS_VERSION,
        qt_version=QT_VERSION_STR,
        qgis_initialised=qgis_initialised,
        plugin_started=plugin_started,
        action_names=action_names,
        action_result=action_result,
        plugin_unloaded=plugin_unloaded,
        owned_resources_released=owned_resources_released,
        qgis_exited=True,
    )


def main() -> int:
    """Run the smoke and print its report as JSON."""
    report = run_smoke()
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
