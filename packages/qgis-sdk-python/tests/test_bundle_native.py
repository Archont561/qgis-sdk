"""A built ZIP installs and loads in a clean QGIS profile (TASK-8 AC4, decision-3).

Opt-in, because it starts the QGIS Desktop binary::

    QGIS_SDK_BUILD_INSTALL=1 QT_QPA_PLATFORM=offscreen pytest tests/test_bundle_native.py

Two plugins are built, unpacked into a fresh profile's ``python/plugins``
the way *Install from ZIP* does, and started inside QGIS Desktop through
``qgis.utils`` while an import hook refuses every ``qgis_sdk`` import: the
plugins must run from their own vendored copies, each a distinct module
tree, and never touch an installed SDK.
"""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest
from qgis_sdk_tools.bundle import VENDOR_PACKAGE, build_plugin
from qgis_sdk_tools.devtools import find_qgis_install
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

pytestmark = pytest.mark.desktop

if not os.environ.get("QGIS_SDK_BUILD_INSTALL"):
    pytest.skip(
        "set QGIS_SDK_BUILD_INSTALL=1 to install a built ZIP into a real QGIS",
        allow_module_level=True,
    )

PLUGINS = ("field_tools", "other_tools")

PROBE = '''"""Start two built plugins in a clean profile with qgis_sdk unavailable."""

import json
import os
import sys
import traceback

REPORT = os.environ["QGIS_SDK_BUILD_REPORT"]
PLUGINS = json.loads(os.environ["QGIS_SDK_BUILD_PLUGINS"])


class RefuseSdk:
    """No plugin may reach an installed SDK: only the vendored copies exist."""

    def find_spec(self, name, path=None, target=None):
        if name == "qgis_sdk" or name.startswith("qgis_sdk."):
            raise ImportError(f"{name} is not available in this QGIS")
        return None


sys.meta_path.insert(0, RefuseSdk())
report = {"error": None}
try:
    import qgis.utils

    qgis.utils.updateAvailablePlugins()
    report["available"] = sorted(p for p in PLUGINS if p in qgis.utils.available_plugins)
    for name in PLUGINS:
        report[f"{name}_loaded"] = bool(qgis.utils.loadPlugin(name))
        report[f"{name}_started"] = bool(qgis.utils.startPlugin(name))
        held = qgis.utils.plugins[name]
        report[f"{name}_ping"] = held.runtime.actions["ping"](41) + 1
        report[f"{name}_runtime_module"] = type(held.runtime).__module__
        report[f"{name}_mark"] = sys.modules[f"{name}._vendor.qgis_sdk"].VENDORED_MARK
    runtimes = [type(qgis.utils.plugins[n].runtime) for n in PLUGINS]
    report["distinct_runtime_classes"] = runtimes[0] is not runtimes[1]
    report["sdk_imported"] = "qgis_sdk" in sys.modules
    report["unloaded"] = [bool(qgis.utils.unloadPlugin(n)) for n in PLUGINS]
except BaseException:  # noqa: BLE001 - the report is the only way out
    report["error"] = traceback.format_exc()
with open(REPORT, "w", encoding="utf-8") as handle:
    json.dump(report, handle)
(sys.__stderr__ or sys.stderr).flush()
os._exit(0 if report["error"] is None else 1)
'''


def never_run(argv: Sequence[str], cwd: Path) -> int:
    raise AssertionError(f"no process expected, got {argv} in {cwd}")


def test_two_built_plugins_load_from_their_own_vendored_runtimes(
    tmp_path: Path,
) -> None:
    install = find_qgis_install(dict(os.environ))
    assert install.executable is not None, "this harness needs QGIS Desktop"
    profiles = tmp_path / "profiles-root"
    plugins_dir = profiles / "profiles" / "build" / "python" / "plugins"
    plugins_dir.mkdir(parents=True)

    for name in PLUGINS:
        root = tmp_path / "src" / name
        write_scaffold(ScaffoldOptions.resolve(name), root)
        result = build_plugin(root, run=never_run)
        with zipfile.ZipFile(result.archive) as zf:
            assert zf.namelist()[0].startswith(f"{name}/")
            zf.extractall(plugins_dir)  # what QGIS's "Install from ZIP" does
        # Stand in for two different SDK versions: mark each vendored copy so
        # the probe can tell which one a plugin's runtime came from.
        vendored_init = plugins_dir / name / VENDOR_PACKAGE / "qgis_sdk" / "__init__.py"
        vendored_init.write_text(
            vendored_init.read_text(encoding="utf-8") + f'\nVENDORED_MARK = "{name}"\n',
            encoding="utf-8",
        )

    probe = tmp_path / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    compile(PROBE, str(probe), "exec")
    report_path = tmp_path / "report.json"
    base = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH"}}
    env = install.environment(base, headless=True, desktop=True)
    env["QGIS_SDK_BUILD_REPORT"] = str(report_path)
    env["QGIS_SDK_BUILD_PLUGINS"] = json.dumps(list(PLUGINS))

    completed = subprocess.run(
        [
            str(install.executable),
            "--profiles-path",
            str(profiles),
            "--profile",
            "build",
            "--code",
            str(probe),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert report_path.is_file(), completed.stdout + completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["error"] is None, report["error"]
    assert completed.returncode == 0
    assert report["available"] == sorted(PLUGINS)
    for name in PLUGINS:
        assert report[f"{name}_loaded"] is True
        assert report[f"{name}_started"] is True
        assert report[f"{name}_ping"] == 42
        assert report[f"{name}_runtime_module"].startswith(
            f"{name}.{VENDOR_PACKAGE}.qgis_sdk."
        )
        assert report[f"{name}_mark"] == name
    assert report["distinct_runtime_classes"] is True
    assert report["sdk_imported"] is False
    assert report["unloaded"] == [True, True]
