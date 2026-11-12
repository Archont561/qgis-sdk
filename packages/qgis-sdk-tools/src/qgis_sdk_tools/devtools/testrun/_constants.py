"""The test runner's constants: targets, selections, lockfiles, the probe."""

from __future__ import annotations

from typing import Final

__all__ = [
    "DESKTOP_PROBE",
    "LOCKFILES",
    "NATIVE_TARGETS",
    "PLUGIN",
    "PROBE_NAME",
    "PROFILE_NAME",
    "REQUEST_ENV",
    "REQUEST_NAME",
    "SELECTION",
    "TARGETS",
]

PLUGIN: Final = "qgis_sdk_tools.pytest_plugin"
TARGETS: Final = ("pure", "qgis", "desktop", "server", "web")
NATIVE_TARGETS: Final = frozenset({"qgis", "desktop", "server"})
PROFILE_NAME: Final = "qgis-sdk-test"
REQUEST_ENV: Final = "QGIS_SDK_TEST_REQUEST"
PROBE_NAME: Final = "pytest-probe.py"
REQUEST_NAME: Final = "pytest-request.json"

SELECTION: Final = {
    "pure": "not qgis and not desktop and not server",
    "qgis": "qgis",
    "desktop": "desktop",
    "server": "server",
}

LOCKFILES: Final = (
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("package-lock.json", "npm"),
)

#: Runs inside the Desktop binary (``qgis --code``). It reads its request from
#: a file because QGIS treats trailing arguments as project paths, and ends the
#: process itself because Desktop would otherwise sit in its event loop.
DESKTOP_PROBE: Final = '''"""Run pytest inside QGIS Desktop and exit with its verdict (qgis-sdk test)."""

import json
import os
import sys

request = json.loads(open(os.environ["QGIS_SDK_TEST_REQUEST"], encoding="utf-8").read())
# QGIS may have hooked the streams for its console; pytest talks to the terminal.
sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
os.chdir(request["cwd"])
sys.path.insert(0, request["cwd"])

try:
    import pytest
except ImportError as error:
    sys.stderr.write(
        "qgis-sdk test: pytest is not importable inside QGIS Desktop's Python "
        f"({sys.executable}): {error}\\n"
    )
    sys.stderr.flush()
    os._exit(4)

code = pytest.main(request["args"])
sys.stdout.flush()
sys.stderr.flush()
os._exit(int(code))
'''
