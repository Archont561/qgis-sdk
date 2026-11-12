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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_two_built_p_p1(_s):
    _s.install = find_qgis_install(dict(os.environ))
    assert _s.install.executable is not None, "this harness needs QGIS Desktop"
    _s.profiles = _s.tmp_path / "profiles-root"
    _s.plugins_dir = _s.profiles / "profiles" / "build" / "python" / "plugins"
    _s.plugins_dir.mkdir(parents=True)


def _cc_test_two_built_p_p2(_s):

    for name in PLUGINS:
        _s.name = name
        _s.root = _s.tmp_path / "src" / _s.name
        write_scaffold(ScaffoldOptions.resolve(_s.name), _s.root)
        _s.result = build_plugin(_s.root, run=never_run)
        with zipfile.ZipFile(_s.result.archive) as _s.zf:
            assert _s.zf.namelist()[0].startswith(f"{_s.name}/")
            _s.zf.extractall(_s.plugins_dir)  # what QGIS's "Install from ZIP" does
        # Stand in for two different SDK versions: mark each vendored copy so
        # the probe can tell which one a plugin's runtime came from.
        _s.vendored_init = (
            _s.plugins_dir / _s.name / VENDOR_PACKAGE / "qgis_sdk" / "__init__.py"
        )
        _s.vendored_init.write_text(
            _s.vendored_init.read_text(encoding="utf-8")
            + f'\nVENDORED_MARK = "{_s.name}"\n',
            encoding="utf-8",
        )


def _cc_test_two_built_p_p3(_s):

    _s.probe = _s.tmp_path / "probe.py"
    _s.probe.write_text(PROBE, encoding="utf-8")
    compile(PROBE, str(_s.probe), "exec")
    _s.report_path = _s.tmp_path / "report.json"
    _s.base = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH"}}
    _s.env = _s.install.environment(_s.base, headless=True, desktop=True)
    _s.env["QGIS_SDK_BUILD_REPORT"] = str(_s.report_path)
    _s.env["QGIS_SDK_BUILD_PLUGINS"] = json.dumps(list(PLUGINS))


def _cc_test_two_built_p_p4(_s):

    _s.completed = subprocess.run(
        [
            str(_s.install.executable),
            "--profiles-path",
            str(_s.profiles),
            "--profile",
            "build",
            "--code",
            str(_s.probe),
        ],
        cwd=_s.tmp_path,
        env=_s.env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _cc_test_two_built_p_p5(_s):

    assert _s.report_path.is_file(), _s.completed.stdout + _s.completed.stderr
    _s.report = json.loads(_s.report_path.read_text(encoding="utf-8"))
    assert _s.report["error"] is None, _s.report["error"]
    assert _s.completed.returncode == 0
    assert _s.report["available"] == sorted(PLUGINS)


def _cc_test_two_built_p_p6(_s):
    for name in PLUGINS:
        _s.name = name
        assert _s.report[f"{_s.name}_loaded"] is True
        assert _s.report[f"{_s.name}_started"] is True
        assert _s.report[f"{_s.name}_ping"] == 42
        assert _s.report[f"{_s.name}_description"] == _s.name
        assert _s.report[f"{_s.name}_action_description"] == "ping"
        assert _s.report[f"{_s.name}_runtime_module"].startswith(
            f"{_s.name}.{VENDOR_PACKAGE}.qgis_sdk."
        )
        assert _s.report[f"{_s.name}_mark"] == _s.name
    assert _s.report["distinct_runtime_classes"] is True
    assert _s.report["sdk_imported"] is False


def _cc_test_two_built_p_p7(_s):
    assert _s.report["unloaded"] == [True, True]


_CC_TEXT_1 = '''"""Start two built plugins in a clean profile with qgis_sdk unavailable."""

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
        # The runtime's validated description, not the private lowered class
        # (decision-67, TASK-141): the application object is not exposed.
        held_description = held.runtime.description
        report[f"{name}_description"] = held_description.id
        report[f"{name}_action_description"] = next(
            action.id for action in held_description.actions if action.id == "ping"
        )
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


pytestmark = pytest.mark.desktop

if not os.environ.get("QGIS_SDK_BUILD_INSTALL"):
    pytest.skip(
        "set QGIS_SDK_BUILD_INSTALL=1 to install a built ZIP into a real QGIS",
        allow_module_level=True,
    )

PLUGINS = ("field_tools", "other_tools")

PROBE = _CC_TEXT_1


def never_run(argv: Sequence[str], cwd: Path) -> int:
    raise AssertionError(f"no process expected, got {argv} in {cwd}")


def test_two_built_plugins_load_from_their_own_vendored_runtimes(
    tmp_path: Path,
) -> None:
    _s = _CcState(tmp_path=tmp_path)
    for _p in (
        _cc_test_two_built_p_p1,
        _cc_test_two_built_p_p2,
        _cc_test_two_built_p_p3,
        _cc_test_two_built_p_p4,
        _cc_test_two_built_p_p5,
        _cc_test_two_built_p_p6,
        _cc_test_two_built_p_p7,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
