"""Prove the Desktop lifecycle adapter on a real QGIS host, with no fake fallback.

TASK-24 AC3 asks for "real Desktop startup/unload evidence with no fake fallback",
which the always-runnable ``desktop_lifecycle_smoke.py`` harness deliberately does not
supply: it constructs the adapter inside a ``QgsApplication`` with ``iface=None`` and
no event loop. This harness closes that gap by writing a small *fixture* plugin that
is bound through ``qgis_sdk.adapters.desktop.host()`` and letting the Desktop
application's own plugin manager start and unload it.

The fixture is not the generated scaffold project. TASK-1 owns that evidence; this
file proves the adapter contract itself, so it depends on ``qgis_sdk`` only and never
on ``qgis_sdk_tools.scaffold``. Every claim is checked against the real host:

* ``iface_is_host`` - the interface the adapter holds *is* ``qgis.utils.iface``, so
  nothing substituted a stand-in; the run fails outright if QGIS offered no iface.
* ``native_context_matches`` - ``ctx.desktop`` hands the author code that same
  live object back through the typed escape hatch.
* ``message_bar_received`` - calling the notifications service actually added a widget
  to QGIS's real message bar, which is the first time that path is exercised at all.
* ``scope_released`` - the plugin's ``ResourceScope`` is closed once QGIS calls
  ``unload``, so what the runtime owned was actually handed back.
* ``actions_detached`` - the runtime's action mapping is empty afterwards, so no stale
  callable survives a Desktop unload.

QGIS's own module cache is deliberately not claimed: ``unloadPlugin`` drops only the
modules ``_plugin_modules`` recorded, which is QGIS bookkeeping rather than something
this SDK promises, so asserting it would prove the wrong thing.

Shared headless-Desktop rules live in ``desktop_smoke_kit``. Offscreen Qt still shows
no window and renders nothing: this qualifies the plugin and lifecycle path, not GUI
behaviour (TASK-33 keeps the display-dependent work).

Run it from the workspace root::

    pixi run -e default python packages/qgis-sdk-python/scripts/desktop_adapter_smoke.py

Exit codes: 0 = the adapter lifecycle passed on a real host, 1 = it failed or QGIS is
unavailable, and the report's ``error`` field says which.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Final

from desktop_smoke_kit import (
    PING_VALUE,
    REPORT_FILE,
    REQUEST_FILE,
    ensure_source_root_on_path,
    profile_plugin_dir,
    qgis_executable,
    read_report,
    run_desktop_probe,
    write_workspace_file,
)

FIXTURE_PLUGIN: Final = "sdk_lifecycle_probe"
FIXTURE_TITLE: Final = "SDK lifecycle probe"
FIXTURE_ID: Final = "sdk.lifecycle.probe"

FIXTURE_INIT: Final = f'''"""QGIS entry point for the SDK Desktop lifecycle fixture.

The one line ``qgis-sdk build`` appends to a staged ``__init__.py``
(decision-43): the runtime's ``host()`` is the ``classFactory``.
"""

from qgis_sdk.adapters.desktop import host

classFactory = host("{FIXTURE_PLUGIN}.plugin:LifecycleProbe")
'''

FIXTURE_METADATA: Final = """[general]
name=SDK lifecycle probe
description=Fixture plugin proving the Desktop adapter lifecycle on a real host.
about=Written by packages/qgis-sdk-python/scripts/desktop_adapter_smoke.py; never shipped.
version=0.0.0
qgisMinimumVersion=4.0
author=qgis-sdk qualification
email=someone@example.invalid
experimental=True
hasProcessingProvider=No
"""

#: The author-side half of the evidence: a plugin class built by the SDK adapter,
#: holding on to nothing but the context it was handed.
FIXTURE_PLUGIN_SOURCE: Final = f'''"""The fixture plugin class the Desktop adapter constructs and disposes."""

from __future__ import annotations

from dataclasses import dataclass

from qgis_sdk import action, plugin
from qgis_sdk.core import PluginContext, ResourceScope

OBSERVED: dict[str, object] = {{}}
"""What the host handed the plugin, so the probe can inspect it after construction."""


class MessageBarNotifications:
    """Send informational messages to the host message bar, if there is one."""

    def __init__(self, iface: object | None) -> None:
        self._iface = iface

    def info(self, message: str) -> None:
        if self._iface is None:
            return
        self._iface.messageBar().pushInfo("{FIXTURE_TITLE}", message)


@dataclass(frozen=True, slots=True)
class IfaceDesktopAccess:
    """The one place this fixture hands the native host object to the SDK."""

    iface: object


def build_context(iface: object) -> PluginContext:
    """Give the plugin exactly the capabilities this host can offer."""
    return PluginContext(
        notifications=MessageBarNotifications(iface),
        scope=ResourceScope(),
        desktop=None if iface is None else IfaceDesktopAccess(iface),
    )


@plugin(id="{FIXTURE_ID}", title="{FIXTURE_TITLE}")
class LifecycleProbe:
    """Record the context it was given and answer one round-trip action."""

    ctx: PluginContext
    context_factory = staticmethod(build_context)

    def __init__(self) -> None:
        OBSERVED["context"] = self.ctx

    @action(id="ping", title="Ping")
    def ping(self, value: int) -> int:
        """Return the value unchanged so a caller can prove the round trip."""
        return value
'''

FIXTURE_FILES: Final = {
    "__init__.py": FIXTURE_INIT,
    "metadata.txt": FIXTURE_METADATA,
    "plugin.py": FIXTURE_PLUGIN_SOURCE,
}

LIFECYCLE_PROBE: Final = '''"""Assert the adapter lifecycle against the live Desktop host."""

import importlib
import json
import os
import platform
import sys
from pathlib import Path

workspace = Path(os.environ["QGIS_SDK_DESKTOP_WORKSPACE"])
request = json.loads((workspace / "request.json").read_text(encoding="utf-8"))
plugin = request["plugin"]
payload = {
    "platform": platform.platform(),
    "python_version": platform.python_version(),
    "qgis_version": None,
    "plugin": plugin,
    "iface_is_host": False,
    "native_context_matches": False,
    "started": False,
    "runtime_running": False,
    "message_bar_received": False,
    "action_result": None,
    "unloaded": False,
    "runtime_stopped": False,
    "scope_released": False,
    "actions_detached": False,
    "error": None,
}

# Mirrored deliberately: the probe cannot import this module, so the suite compares
# the two lists instead of trusting a shared constant.
EVIDENCE = (
    "iface_is_host",
    "native_context_matches",
    "started",
    "runtime_running",
    "message_bar_received",
    "unloaded",
    "runtime_stopped",
    "scope_released",
    "actions_detached",
)


def finish(code: int) -> None:
    with (workspace / "report.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os._exit(code)


def missing() -> list[str]:
    """Return the stages a real host did not confirm; empty means all confirmed."""
    return [key for key in EVIDENCE if payload[key] is not True]


try:
    import qgis.utils
    from qgis.core import Qgis

    payload["qgis_version"] = Qgis.QGIS_VERSION
    host = qgis.utils.iface
    if host is None:
        payload["error"] = "QGIS provided no interface object, so there is nothing to qualify"
        finish(1)

    # The sequence QGIS's own startup loop and Plugins dialog use, in that order.
    payload["started"] = bool(
        qgis.utils.loadPlugin(plugin)
        and qgis.utils.startPlugin(plugin)
        and qgis.utils.isPluginLoaded(plugin)
    )
    if not payload["started"]:
        payload["error"] = "QGIS could not start the fixture plugin"
        finish(1)

    adapter = qgis.utils.plugins[plugin]
    payload["iface_is_host"] = adapter.iface is host
    payload["runtime_running"] = adapter.runtime.state.value == "running"

    module = importlib.import_module(plugin + ".plugin")
    context = module.OBSERVED["context"]
    payload["native_context_matches"] = context.desktop.iface is host

    # The notifications service must reach the host's own bar, not a stand-in.
    bar = host.messageBar()
    before = len(bar.children())
    context.notifications.info("lifecycle probe")
    payload["message_bar_received"] = len(bar.children()) > before

    payload["action_result"] = adapter.runtime.actions["ping"](request["ping_value"])
    payload["unloaded"] = bool(
        qgis.utils.unloadPlugin(plugin) and not qgis.utils.isPluginLoaded(plugin)
    )
    payload["runtime_stopped"] = adapter.runtime.state.value == "stopped"
    payload["scope_released"] = bool(context.scope.closed)
    payload["actions_detached"] = len(adapter.runtime.actions) == 0
except BaseException as error:  # noqa: BLE001 - the report file is the only way out
    payload["error"] = f"{type(error).__name__}: {error}"
    finish(1)

absent = missing()
if absent:
    payload["error"] = "the real host did not confirm: " + ", ".join(absent)
    finish(1)

finish(0)
'''

REPORT_FIELDS: Final = (
    "platform",
    "python_version",
    "qgis_version",
    "plugin",
    "iface_is_host",
    "native_context_matches",
    "started",
    "runtime_running",
    "message_bar_received",
    "action_result",
    "unloaded",
    "runtime_stopped",
    "scope_released",
    "actions_detached",
    "error",
)

#: The stages a real host has to confirm; a run that skips one has not passed.
EVIDENCE_FIELDS: Final = (
    "iface_is_host",
    "native_context_matches",
    "started",
    "runtime_running",
    "message_bar_received",
    "unloaded",
    "runtime_stopped",
    "scope_released",
    "actions_detached",
)


@dataclass(frozen=True)
class DesktopAdapterReport:
    """What a real QGIS Desktop run observed for the lifecycle adapter."""

    platform: str
    python_version: str
    qgis_version: str | None
    plugin: str
    iface_is_host: bool
    native_context_matches: bool
    started: bool
    runtime_running: bool
    message_bar_received: bool
    action_result: int | None
    unloaded: bool
    runtime_stopped: bool
    scope_released: bool
    actions_detached: bool
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether every stage was confirmed by the live host."""
        confirmed = all(getattr(self, name) for name in EVIDENCE_FIELDS)
        return confirmed and self.action_result == PING_VALUE

    @classmethod
    def unavailable(cls, error: str | None = None) -> DesktopAdapterReport:
        """Return the report for a run that could observe nothing."""
        return cls(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            plugin=FIXTURE_PLUGIN,
            iface_is_host=False,
            native_context_matches=False,
            started=False,
            runtime_running=False,
            message_bar_received=False,
            action_result=None,
            unloaded=False,
            runtime_stopped=False,
            scope_released=False,
            actions_detached=False,
            error=error,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> DesktopAdapterReport:
        """Build a report from a probe's JSON, ignoring anything unexpected."""
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in known})

    def to_payload(self) -> dict[str, object]:
        """Return the report as JSON-compatible data, including the verdict."""
        return {**asdict(self), "passed": self.passed}


def request_document(plugins_root: Path) -> str:
    """Return the probe's sidecar: a path and a number, nothing generated."""
    return json.dumps(
        {
            "plugin": FIXTURE_PLUGIN,
            "plugins_root": str(plugins_root),
            "ping_value": PING_VALUE,
        }
    )


def install_fixture(plugins_root: Path) -> Path:
    """Write the fixture package where the profile's plugin manager will find it."""
    package = plugins_root / FIXTURE_PLUGIN
    package.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(FIXTURE_FILES.items()):
        (package / name).write_text(text, encoding="utf-8", newline="\n")
    return package


def _run_lifecycle(
    executable: Path, prefix: Path, workspace: Path
) -> DesktopAdapterReport:
    """Install the fixture, then drive one start-and-unload cycle in Desktop."""
    ensure_source_root_on_path()
    plugins_root = profile_plugin_dir(executable, prefix, workspace)
    install_fixture(plugins_root)

    write_workspace_file(workspace, REQUEST_FILE, request_document(plugins_root))
    probe = write_workspace_file(workspace, "adapter-probe.py", LIFECYCLE_PROBE)
    run_desktop_probe(executable, prefix, workspace, probe)

    payload = read_report(workspace)
    if payload is None:
        return DesktopAdapterReport.unavailable(
            f"the Desktop probe wrote no {REPORT_FILE}"
        )
    return DesktopAdapterReport.from_payload(payload)


def run_smoke(prefix: Path | None = None) -> DesktopAdapterReport:
    """Drive one real-Desktop adapter lifecycle, or record why it could not run."""
    prefix = prefix or Path(sys.prefix)
    executable = qgis_executable(prefix)
    if not executable.is_file():
        return DesktopAdapterReport.unavailable(
            f"QGIS Desktop executable not found: {executable}"
        )
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-adapter-"))
    try:
        return _run_lifecycle(executable, prefix, workspace)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return DesktopAdapterReport.unavailable(f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    """Print the report and exit non-zero when the host did not confirm everything."""
    parser = argparse.ArgumentParser(
        description="Prove the Desktop adapter lifecycle in real QGIS (headless)."
    )
    parser.add_argument(
        "--prefix", type=Path, default=None, help="QGIS install prefix."
    )
    arguments = parser.parse_args()
    report = run_smoke(prefix=arguments.prefix)
    print(json.dumps(report.to_payload(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
