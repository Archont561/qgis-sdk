"""Load and unload a generated plugin inside a real QGIS Desktop run (TASK-1 AC2).

This is TASK-1 AC2's evidence: the generated plugin is placed in a clean profile's
user-plugin directory and QGIS's own plugin machinery parses ``metadata.txt``
(``qgis.utils.findPlugins``), starts the plugin (``loadPlugin`` + ``startPlugin``)
and unloads it (``unloadPlugin``) - the same calls the Plugins dialog makes.

The headless Desktop rules - ``QT_QPA_PLATFORM=offscreen``, a placeholder
``DISPLAY``, ``PYTHONHOME`` at the live prefix, and the probe/report exchange - are
in ``desktop_smoke_kit``, which ``desktop_adapter_smoke.py`` also uses. This proves
the Desktop plugin path, not GUI or rendering qualification (see ``doc-8`` and
TASK-33).

Run it from the workspace root with the default Pixi environment::

    pixi run -e default python packages/qgis-sdk-python/scripts/scaffold_desktop_smoke.py

The report helpers and the probe source are pure, so the QGIS-free suite can test
them; the end-to-end run is opt-in through
``tests/scripts/test_qualification_scaffold.py``.

Exit codes: 0 = the Desktop lifecycle passed, 1 = it failed or QGIS is unavailable,
in which case the report's ``error`` field records which, so the gap is reported
rather than hidden.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, fields, replace
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

DEFAULT_PLUGIN: Final = "scaffold_demo"
EXPECTED_MINIMUM_VERSION: Final = "4.0"

#: The metadata fields whose values the Desktop parser has to read back.
METADATA_KEYS: Final = ("name", "qgisMinimumVersion")

LIFECYCLE_PROBE: Final = '''"""Drive the generated plugin through the Desktop application's plugin machinery."""

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
    "discovered": False,
    "metadata_matches": False,
    "loaded": False,
    "runtime_running": False,
    "action_result": None,
    "unloaded": False,
    "runtime_stopped": False,
    "error": None,
}


def finish(code: int) -> None:
    with (workspace / "report.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os._exit(code)


try:
    import qgis.utils
    from qgis.core import Qgis

    payload["qgis_version"] = Qgis.QGIS_VERSION

    # Exactly the sequence QGIS's own startup loop and Plugins dialog use.
    found = dict(qgis.utils.findPlugins(request["plugins_root"]))
    payload["discovered"] = plugin in found
    parser = found.get(plugin)
    if parser is not None:
        read = {key: parser["general"].get(key) for key in request["metadata_keys"]}
        payload["metadata_matches"] = read == request["expected_metadata"]
    payload["loaded"] = bool(
        qgis.utils.loadPlugin(plugin)
        and qgis.utils.startPlugin(plugin)
        and qgis.utils.isPluginLoaded(plugin)
    )
    if payload["loaded"]:
        adapter = qgis.utils.plugins[plugin]
        payload["runtime_running"] = adapter.runtime.state.value == "running"
        payload["action_result"] = adapter.runtime.actions["ping"](request["ping_value"])
        payload["unloaded"] = bool(
            qgis.utils.unloadPlugin(plugin) and not qgis.utils.isPluginLoaded(plugin)
        )
        payload["runtime_stopped"] = adapter.runtime.state.value == "stopped"
except BaseException as error:  # noqa: BLE001 - the report file is the only way out
    payload["error"] = f"{type(error).__name__}: {error}"
    finish(1)

finish(0)
'''

REPORT_FIELDS: Final = (
    "platform",
    "python_version",
    "qgis_version",
    "plugin",
    "discovered",
    "metadata_matches",
    "loaded",
    "runtime_running",
    "action_result",
    "unloaded",
    "runtime_stopped",
    "error",
)


@dataclass(frozen=True)
class DesktopScaffoldReport:
    """What a real QGIS Desktop run observed for one generated plugin."""

    platform: str
    python_version: str
    qgis_version: str | None
    plugin: str
    discovered: bool
    metadata_matches: bool
    loaded: bool
    runtime_running: bool
    action_result: int | None
    unloaded: bool
    runtime_stopped: bool
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether Desktop discovered, started, drove and released it."""
        return (
            self.discovered
            and self.metadata_matches
            and self.loaded
            and self.runtime_running
            and self.action_result == PING_VALUE
            and self.unloaded
            and self.runtime_stopped
        )

    @classmethod
    def unavailable(
        cls, plugin: str, error: str | None = None
    ) -> DesktopScaffoldReport:
        """Return the report for a run that could observe nothing."""
        return cls(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            plugin=plugin,
            discovered=False,
            metadata_matches=False,
            loaded=False,
            runtime_running=False,
            action_result=None,
            unloaded=False,
            runtime_stopped=False,
            error=error,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> DesktopScaffoldReport:
        """Build a report from a probe's JSON, ignoring anything unexpected."""
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in known})

    def to_payload(self) -> dict[str, object]:
        """Return the report as JSON-compatible data, including the verdict."""
        return {**asdict(self), "passed": self.passed}


def expected_metadata(title: str) -> dict[str, str]:
    """Return the metadata QGIS has to read back from the generated plugin."""
    return {"name": title, "qgisMinimumVersion": EXPECTED_MINIMUM_VERSION}


def request_document(plugins_root: Path, plugin: str, title: str) -> str:
    """Return the probe's sidecar: paths and expectations, nothing generated.

    The probe reads it instead of being interpolated, so the probe source stays a
    literal that the suite can parse and assert on without a display.
    """
    return json.dumps(
        {
            "plugin": plugin,
            "plugins_root": str(plugins_root),
            "metadata_keys": list(METADATA_KEYS),
            "expected_metadata": expected_metadata(title),
            "ping_value": PING_VALUE,
        }
    )


def plugin_title(plugin: str) -> str:
    """Return the display title the scaffold derives from a package name."""
    return " ".join(word.title() for word in plugin.split("_"))


def _run_lifecycle(
    executable: Path, prefix: Path, workspace: Path, plugin: str, title: str
) -> DesktopScaffoldReport:
    """Generate the project, install it into the profile, then drive it in Desktop."""
    ensure_source_root_on_path()
    from qgis_sdk.scaffold import ScaffoldOptions, write_scaffold

    project = workspace / "project"
    write_scaffold(ScaffoldOptions.resolve(plugin), project)
    plugins_root = profile_plugin_dir(executable, prefix, workspace)
    plugins_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project / plugin, plugins_root / plugin)

    write_workspace_file(
        workspace, REQUEST_FILE, request_document(plugins_root, plugin, title)
    )
    probe = write_workspace_file(workspace, "lifecycle-probe.py", LIFECYCLE_PROBE)
    run_desktop_probe(executable, prefix, workspace, probe)

    payload = read_report(workspace)
    if payload is None:
        return DesktopScaffoldReport.unavailable(
            plugin, f"the Desktop probe wrote no {REPORT_FILE}"
        )
    return DesktopScaffoldReport.from_payload(payload)


def run_smoke(
    prefix: Path | None = None, plugin: str = DEFAULT_PLUGIN
) -> DesktopScaffoldReport:
    """Generate the scaffold and drive one Desktop load and unload cycle."""
    prefix = prefix or Path(sys.prefix)
    executable = qgis_executable(prefix)
    failed = DesktopScaffoldReport.unavailable(plugin)
    if not executable.is_file():
        return replace(failed, error=f"QGIS Desktop executable not found: {executable}")
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-scaffold-"))
    try:
        return _run_lifecycle(
            executable, prefix, workspace, plugin, plugin_title(plugin)
        )
    except Exception as error:  # noqa: BLE001 - report broken environments
        return replace(failed, error=f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    """Print the report and exit non-zero when the cycle did not pass."""
    parser = argparse.ArgumentParser(
        description="Load and unload a generated plugin in QGIS Desktop (headless)."
    )
    parser.add_argument(
        "--prefix", type=Path, default=None, help="QGIS install prefix."
    )
    parser.add_argument(
        "--plugin", default=DEFAULT_PLUGIN, help="Plugin package name to generate."
    )
    arguments = parser.parse_args()
    report = run_smoke(prefix=arguments.prefix, plugin=arguments.plugin)
    print(json.dumps(report.to_payload(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
