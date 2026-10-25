"""Shared machinery for qualification harnesses that drive the QGIS Desktop binary.

Two harnesses need the same awkward setup, so it lives here once:

* ``scripts/scaffold_desktop_smoke.py`` proves a *generated* project is loadable
  (TASK-1), and
* ``scripts/desktop_adapter_smoke.py`` proves the *native lifecycle adapter* starts
  and releases a plugin on a real host (TASK-24).

Both run the Desktop application headless against a clean throwaway profile, hand it
a static probe file, and read a fixed-name JSON report back. Keeping the
environment rules in one place matters because they are not obvious: QGIS refuses to
start without ``DISPLAY``, and a relocated install cannot initialise its embedded
interpreter without ``PYTHONHOME``.

The probes are static source strings that interpolate nothing. They find their
inputs by name under ``$QGIS_SDK_DESKTOP_WORKSPACE`` because ``qgis --code <file>``
treats any trailing argument as a project path, so they take no argv. A harness and
its sibling both resolve paths from ``__file__``, which is why this module is
importable by name from ``scripts`` (see ``tests/conftest.py``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

HEADLESS_PLATFORM: Final = "offscreen"
# QGIS refuses to start when it decides it is non-interactive, which it judges by
# ``DISPLAY`` being unset. The offscreen Qt platform plugin means nothing ever
# connects to that address; the value only satisfies the application's own guard.
PLACEHOLDER_DISPLAY: Final = ":99"

PROFILE_NAME: Final = "sdk-qualification"
WORKSPACE_ENV_VAR: Final = "QGIS_SDK_DESKTOP_WORKSPACE"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The runtime and the tools are separate distributions (decision-35); both go
# on the path so the probe imports the trees under test.
SOURCE_ROOTS = (
    PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src",
    PROJECT_ROOT.parent / "qgis-sdk-tools" / "src",
)

#: The value one probe asks a declared action to return unchanged, so a matching
#: number proves the call travelled through the runtime and back.
PING_VALUE: Final = 7
DESKTOP_TIMEOUT_SECONDS: Final = 300

#: File names a probe exchanges with its harness inside the workspace directory.
REQUEST_FILE: Final = "request.json"
REPORT_FILE: Final = "report.json"
PROFILE_ANSWER_FILE: Final = "profile-dir.txt"


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

    ``SOURCE_ROOTS`` go on ``PYTHONPATH`` so the probe imports the ``qgis_sdk``
    and ``qgis_sdk_tools`` under test rather than installed copies, which is
    what makes the evidence describe this working tree.
    """
    python_path = [str(qgis_python_path(prefix)), *map(str, SOURCE_ROOTS)]
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


def desktop_command(
    executable: Path, workspace: Path, probe: Path, *, profile: str = PROFILE_NAME
) -> list[str]:
    """Return the QGIS Desktop invocation that runs one probe and loads nothing.

    ``--noplugins`` keeps the run deterministic: the only plugin in the profile is
    the one the harness installed, so a load cannot succeed by accident.
    """
    return [
        str(executable),
        "--noplugins",
        "--profiles-path",
        str(workspace / "profiles"),
        "--profile",
        profile,
        "--code",
        str(probe),
    ]


def write_workspace_file(workspace: Path, name: str, text: str) -> Path:
    """Write one file into the exchange directory with LF endings."""
    path = workspace / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def run_desktop_probe(
    executable: Path, prefix: Path, workspace: Path, probe: Path
) -> None:
    """Start QGIS Desktop once with one probe and wait for the probe to exit."""
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


def profile_plugin_dir(executable: Path, prefix: Path, workspace: Path) -> Path:
    """Ask a first Desktop run where user plugins belong, so nothing is guessed.

    The answer comes from ``qgis.utils.HOME_PLUGIN_PATH`` inside the application
    itself: the profile layout is QGIS's business, and a harness that inferred
    ``profiles/profiles/<name>/python/plugins`` would be proving its own guess.
    """
    probe = write_workspace_file(workspace, "profile-probe.py", PROFILE_PROBE)
    run_desktop_probe(executable, prefix, workspace, probe)
    answer = workspace / PROFILE_ANSWER_FILE
    if not answer.is_file():
        failure = workspace / "profile-error.txt"
        detail = (
            failure.read_text(encoding="utf-8") if failure.is_file() else "no answer"
        )
        raise RuntimeError(
            f"QGIS Desktop did not report its user plugin directory: {detail}"
        )
    return Path(answer.read_text(encoding="utf-8").strip())


PROFILE_PROBE: Final = '''"""Ask the Desktop application where user plugins belong."""

import os
from pathlib import Path

workspace = Path(os.environ["QGIS_SDK_DESKTOP_WORKSPACE"])

try:
    from qgis.utils import HOME_PLUGIN_PATH

    (workspace / "profile-dir.txt").write_text(str(HOME_PLUGIN_PATH), encoding="utf-8")
except BaseException as error:  # noqa: BLE001 - the answer file is the only way out
    (workspace / "profile-error.txt").write_text(repr(error), encoding="utf-8")

# QGIS would otherwise stay open in its GUI loop: this process has answered, and the
# Desktop binary offers no way to be told to quit, so the probe ends the process.
os._exit(0)
'''


def write_request(workspace: Path, payload: dict[str, object]) -> Path:
    """Write the probe's sidecar: paths and expectations, nothing generated."""
    return write_workspace_file(
        workspace, REQUEST_FILE, json.dumps(payload, sort_keys=True)
    )


def read_report(workspace: Path) -> dict[str, object] | None:
    """Return the probe's report, or None when the probe never got that far."""
    path = workspace / REPORT_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_source_root_on_path() -> None:
    """Make the ``qgis_sdk`` under test importable from this working tree."""
    for root in reversed(SOURCE_ROOTS):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
