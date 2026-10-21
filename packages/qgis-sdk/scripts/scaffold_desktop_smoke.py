"""Generate the scaffold, then load and unload it inside a real QGIS Desktop run.

This is TASK-1 AC2's evidence: the generated plugin is placed in a clean profile's
user-plugin directory and QGIS's own plugin machinery parses ``metadata.txt``
(``qgis.utils.findPlugins``), starts the plugin (``startPlugin``) and unloads it
(``unloadPlugin``) - the same calls the Plugins dialog makes.

There is **no display**, and running the Desktop binary headless needs three
variables that are easy to get wrong, which is why they are set here rather than
in a recipe: ``QT_QPA_PLATFORM=offscreen`` (no window system, nothing rendered),
``DISPLAY`` (QGIS refuses to start when it judges itself non-interactive, and it
judges that from ``DISPLAY`` alone - with the offscreen platform nothing ever
connects to the placeholder address) and ``PYTHONHOME`` (QGIS carries its
build-time prefix in the embedded interpreter, so a relocated install starts and
then cannot even ``import sys``). So this proves the Desktop plugin path, not GUI
or rendering qualification (see ``doc-8`` and TASK-33).

Run it from the workspace root with the default Pixi environment::

    pixi run -e default python packages/qgis-sdk/scripts/scaffold_desktop_smoke.py

The report helpers and the two probe sources are pure, so the QGIS-free suite can
test them; the end-to-end run is opt-in through
``tests/scripts/test_qualification_scaffold.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final

HEADLESS_PLATFORM: Final = "offscreen"
# QGIS refuses to start when it decides it is non-interactive, which it judges by
# ``DISPLAY`` being unset. The offscreen Qt platform plugin means nothing ever
# connects to that address; the value only satisfies the application's own guard.
PLACEHOLDER_DISPLAY: Final = ":99"
PROFILE_NAME: Final = "sdk-scaffold"
WORKSPACE_ENV_VAR: Final = "QGIS_SDK_SCAFFOLD_WORKSPACE"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
DEFAULT_PLUGIN: Final = "scaffold_demo"
EXPECTED_MINIMUM_VERSION: Final = "4.0"
PING_VALUE: Final = 7
DESKTOP_TIMEOUT_SECONDS: Final = 300

#: Both probes are written verbatim into the workspace and executed by
#: ``qgis --code``. They take no arguments and interpolate nothing: they find
#: their inputs by name under ``$QGIS_SDK_SCAFFOLD_WORKSPACE``, so the same text
#: can be parsed and asserted on without a display.
PROFILE_PROBE: Final = '''"""Ask the Desktop application where user plugins belong."""

import os
from pathlib import Path

workspace = Path(os.environ["QGIS_SDK_SCAFFOLD_WORKSPACE"])

from qgis.utils import HOME_PLUGIN_PATH

with (workspace / "profile-dir.txt").open("w", encoding="utf-8") as handle:
    handle.write(str(HOME_PLUGIN_PATH))
    handle.flush()
    os.fsync(handle.fileno())
os._exit(0)
'''

LIFECYCLE_PROBE: Final = '''"""Drive the generated plugin through the Desktop application's plugin machinery."""

import json
import os
import platform
import sys
from pathlib import Path

workspace = Path(os.environ["QGIS_SDK_SCAFFOLD_WORKSPACE"])
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

#: The metadata fields whose values the Desktop parser has to read back.
METADATA_KEYS: Final = ("name", "qgisMinimumVersion")


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
        """Build the report from the probe's JSON, which owns its own keys."""
        return cls(
            **{  # type: ignore[arg-type]
                field: payload[field] for field in REPORT_FIELDS if field in payload
            }
        )

    def to_payload(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable mapping."""
        report = asdict(self)
        report["passed"] = self.passed
        return report


def qgis_python_path(prefix: Path) -> Path:
    """Return the directory holding the QGIS Python bindings of a prefix."""
    return prefix / "share" / "qgis" / "python"


def qgis_executable(prefix: Path) -> Path:
    """Return the Desktop application binary of a prefix."""
    return prefix / "bin" / "qgis"


def headless_environment(prefix: Path, environ: dict[str, str]) -> dict[str, str]:
    """Return the overrides a headless Desktop plugin run needs.

    ``PYTHONHOME`` is not decoration: QGIS carries the *build-time* prefix in its
    embedded interpreter, and a relocated or restored environment leaves that path
    pointing somewhere that no longer exists, so the app starts and then cannot even
    ``import sys``. Pointing it at the live prefix is what makes ``--code`` run.
    """
    python_path = [str(qgis_python_path(prefix)), str(SOURCE_ROOT)]
    existing = environ.get("PYTHONPATH")
    if existing:
        python_path.append(existing)
    return {
        "QT_QPA_PLATFORM": HEADLESS_PLATFORM,
        "PROJ_LIB": str(prefix / "share" / "proj"),
        "QGIS_PREFIX_PATH": str(prefix),
        "PYTHONPATH": os.pathsep.join(python_path),
        "PYTHONHOME": str(prefix),
        "DISPLAY": PLACEHOLDER_DISPLAY,
    }


def desktop_command(executable: Path, workspace: Path, probe: Path) -> list[str]:
    """Return the QGIS Desktop invocation that runs one probe and loads nothing."""
    return [
        str(executable),
        "--noplugins",
        "--profiles-path",
        str(workspace / "profiles"),
        "--profile",
        PROFILE_NAME,
        "--code",
        str(probe),
    ]


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


def _write(workspace: Path, name: str, text: str) -> Path:
    path = workspace / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _desktop_run(executable: Path, prefix: Path, workspace: Path, probe: Path) -> None:
    """Start QGIS Desktop once with one probe and wait for it to finish."""
    environment = headless_environment(prefix, dict(os.environ))
    environment["HOME"] = str(workspace / "home")
    environment[WORKSPACE_ENV_VAR] = str(workspace)
    subprocess.run(
        desktop_command(executable, workspace, probe),
        env=environment,
        capture_output=True,
        text=True,
        timeout=DESKTOP_TIMEOUT_SECONDS,
        check=False,
    )


def _profile_plugin_dir(executable: Path, prefix: Path, workspace: Path) -> Path:
    """Ask a first Desktop run where user plugins belong, so nothing is guessed."""
    probe = _write(workspace, "profile-probe.py", PROFILE_PROBE)
    _desktop_run(executable, prefix, workspace, probe)
    answer = workspace / "profile-dir.txt"
    if not answer.is_file():
        raise RuntimeError("QGIS Desktop did not report its user plugin directory")
    return Path(answer.read_text(encoding="utf-8").strip())


def _run_lifecycle(
    executable: Path, prefix: Path, workspace: Path, plugin: str, title: str
) -> DesktopScaffoldReport:
    """Generate the project, install it into the profile, then drive it in Desktop."""
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    from qgis_sdk.scaffold import ScaffoldOptions, write_scaffold

    project = workspace / "project"
    write_scaffold(ScaffoldOptions.resolve(plugin), project)
    plugins_root = _profile_plugin_dir(executable, prefix, workspace)
    plugins_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project / plugin, plugins_root / plugin)

    _write(workspace, "request.json", request_document(plugins_root, plugin, title))
    probe = _write(workspace, "lifecycle-probe.py", LIFECYCLE_PROBE)
    _desktop_run(executable, prefix, workspace, probe)

    report = workspace / "report.json"
    if not report.is_file():
        return DesktopScaffoldReport.unavailable(
            plugin, "the Desktop probe wrote no report file"
        )
    return DesktopScaffoldReport.from_payload(
        json.loads(report.read_text(encoding="utf-8"))
    )


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
