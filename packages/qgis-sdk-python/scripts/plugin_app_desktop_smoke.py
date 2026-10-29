"""Run the application API inside actual QGIS Desktop.

Uses a throwaway QGIS profile and offscreen Qt. This exercises QGIS's real
plugin manager and iface, but does not qualify visible GUI rendering or ZIPs.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from desktop_smoke_kit import (
    profile_plugin_dir,
    qgis_executable,
    read_report,
    run_desktop_probe,
    write_request,
    write_workspace_file,
)

EVIDENCE_FIELDS = (
    "discovered",
    "real_iface",
    "both_loaded",
    "native_context",
    "provider_registration",
    "actions_and_dialogs",
    "surface_wire_dispatch",
    "surface_direct_capabilities",
    "surface_navigation",
    "closed_view_capabilities",
    "first_unload_isolated",
    "reload_fresh_module",
    "final_cleanup",
    "direct_app_spec_resolved",
)

PLUGIN_SOURCE = """\
from qgis.PyQt.QtCore import QThread
from qgis.PyQt.QtWidgets import QApplication, QLabel, QPushButton
from qgis_sdk import QgisSdkPlugin, menu, shortcut, toolbar
from qgis_sdk.core import PluginContext
from qgis_sdk.providers import Provider
from qgis_sdk.ui import Dialog, on

calls = []
closed = []
wire_results = []
capability_results = []
child = QgisSdkPlugin(id="application.NAME.child")

@child.surface
class Detail(Dialog):
    title = "Details"
    def build(self):
        return QLabel("details")

@child.surface
class Report(Dialog):
    title = "Application report"
    def build(self):
        button = QPushButton("Run")
        button.setObjectName("go")
        return button
    @on("go").clicked
    def run_clicked(self):
        wire_results.append(self.ctx.actions.double(value=21))
        capability_results.append((self.ctx.desktop.iface, self.ctx.algorithms.describe("native:buffer").id, self.ctx.styles))
        self.ctx.ui.open(Detail)
    def on_close(self):
        closed.append(True)

child.add_provider(Provider(id="applicationproofNAME", title="Application NAME"))

@toolbar
@menu("Plugins/Application NAME")
@shortcut("Ctrl+Alt+KEY")
@child.action(id="show", title="Show")
def show(ctx: PluginContext) -> None:
    calls.append(QThread.currentThread() == QApplication.instance().thread())
    ctx.ui.open(Report)

@child.action(id="double", title="Double")
def double(ctx: PluginContext, value: int) -> int:
    return value * 2

app = QgisSdkPlugin(id="application.NAME", title="Application NAME")
app.include(child)

"""

PROBE = """\
import importlib
import json
import os
import platform
import sys
from pathlib import Path

workspace = Path(os.environ["QGIS_SDK_DESKTOP_WORKSPACE"])
request = json.loads((workspace / "request.json").read_text(encoding="utf-8"))
sys.path.insert(0, request["scripts"])
result = {"platform": platform.platform(), "python_version": platform.python_version(), "error": None}

try:
    import qgis.utils as utils
    from qgis.core import Qgis, QgsApplication
    from qgis.PyQt.QtCore import QT_VERSION_STR
    from qgis.PyQt.QtWidgets import QPushButton
    from qgis_sdk.adapters.desktop import host

    result["qgis_version"] = Qgis.QGIS_VERSION
    result["qt_version"] = QT_VERSION_STR
    result["real_iface"] = utils.iface is not None and utils.iface.mainWindow() is not None
    names = request["names"]
    utils.updateAvailablePlugins()
    result["discovered"] = all(name in utils.available_plugins for name in names)
    result["both_loaded"] = all(utils.loadPlugin(name) and utils.startPlugin(name) and utils.isPluginLoaded(name) for name in names)
    if not result["both_loaded"]:
        raise RuntimeError("QGIS plugin manager failed to start the fixture apps")
    first, second = (utils.plugins[name] for name in names)
    modules = [importlib.import_module(name + ".plugin") for name in names]
    registry = QgsApplication.processingRegistry()
    result["native_context"] = all(plugin.iface is utils.iface and plugin.context.desktop.iface is utils.iface and plugin.context.has("layers") for plugin in (first, second))
    result["provider_registration"] = all(registry.providerById("applicationproof" + suffix) is not None for suffix in ("one", "two"))
    for plugin in (first, second):
        plugin.desktop_bindings.placed[0].trigger()
    result["actions_and_dialogs"] = all(module.calls == [True] and len(plugin.surfaces.dialogs) == 1 and plugin.runtime.actions["double"](value=21) == 42 for plugin, module in zip((first, second), modules))
    for plugin in (first, second):
        button = plugin.surfaces.dialogs[0].widget.findChild(QPushButton, "go")
        if button is None:
            raise RuntimeError("wired button was not mounted")
        button.click()
    result["surface_wire_dispatch"] = all(module.wire_results == [42] for module in modules)
    result["surface_direct_capabilities"] = all(len(module.capability_results) == 1 and module.capability_results[0][0] is utils.iface and module.capability_results[0][1] == "native:buffer" and module.capability_results[0][2] is plugin.context.styles for plugin, module in zip((first, second), modules))
    result["surface_navigation"] = all(len(plugin.surfaces.dialogs) == 2 and isinstance(plugin.surfaces.dialogs[1].surface, module.Detail) for plugin, module in zip((first, second), modules))
    result["direct_app_spec_resolved"] = callable(host(names[0] + ".plugin:app"))
    closed_view_ctx = first.surfaces.dialogs[0].surface.ctx
    unloaded = utils.unloadPlugin(names[0]) and not utils.isPluginLoaded(names[0])
    from qgis_sdk.models import QgisSdkScopeClosedError
    closed_refusals = []
    for name in ("algorithms", "styles", "desktop", "ui"):
        try:
            getattr(closed_view_ctx, name)
        except QgisSdkScopeClosedError:
            closed_refusals.append(name)
    result["closed_view_capabilities"] = len(closed_refusals) == 4 and second.surfaces.dialogs[0].surface.ctx.desktop.iface is utils.iface
    result["first_unload_isolated"] = bool(unloaded and first.context.scope.closed and modules[0].closed == [True] and registry.providerById("applicationproofone") is None and registry.providerById("applicationprooftwo") is not None and second.runtime.state.value == "running" and len(second.desktop_bindings.placed) == 1)
    second.desktop_bindings.placed[0].trigger()
    source_path = Path(request["plugins_root"]) / names[0] / "plugin.py"
    source = source_path.read_text(encoding="utf-8")
    if source.count("return value * 2") != 1:
        raise RuntimeError("cannot update the expected action source")
    # The extra line changes file size, so timestamp-granularity cannot reuse a stale pyc.
    source_path.write_text(source.replace("return value * 2", "return value * 3") + "\\n# changed\\n", encoding="utf-8")
    first_again = utils.loadPlugin(names[0]) and utils.startPlugin(names[0])
    new_module = importlib.import_module(names[0] + ".plugin") if first_again else None
    reload_value = utils.plugins[names[0]].runtime.actions["double"](value=21) if first_again else None
    result["reload_details"] = {"started": bool(first_again), "fresh_module": new_module is not modules[0], "action_result": reload_value, "second_calls": modules[1].calls}
    result["reload_fresh_module"] = bool(first_again and new_module is not modules[0] and reload_value == 63 and modules[1].calls == [True, True])
    restarted = utils.plugins[names[0]] if first_again else None
    stop_first = bool(utils.unloadPlugin(names[0])) if first_again else False
    stop_second = bool(utils.unloadPlugin(names[1]))
    result["final_cleanup"] = bool(stop_first and stop_second and restarted is not None and restarted.context.scope.closed and second.context.scope.closed and modules[1].closed == [True, True] and registry.providerById("applicationproofone") is None and registry.providerById("applicationprooftwo") is None and not second.desktop_bindings.placed)
except BaseException as error:
    result["error"] = f"{type(error).__name__}: {error}"

with (workspace / "report.json").open("w", encoding="utf-8") as handle:
    json.dump(result, handle)
    handle.flush()
    os.fsync(handle.fileno())
os._exit(0 if result["error"] is None else 1)
"""


def passed(payload: dict[str, object]) -> bool:
    """Fail unless every named evidence item is explicitly true."""
    return payload.get("error") is None and all(
        payload.get(field) is True for field in EVIDENCE_FIELDS
    )


def run_smoke(prefix: Path | None = None) -> dict[str, object]:
    """Launch QGIS Desktop with two throwaway application plugins."""
    prefix = prefix or Path(sys.prefix)
    executable = qgis_executable(prefix)
    if not executable.is_file():
        return {"passed": False, "error": f"QGIS Desktop not found: {executable}"}
    with tempfile.TemporaryDirectory(prefix="qgis-sdk-app-desktop-") as temporary:
        workspace = Path(temporary)
        try:
            root = profile_plugin_dir(executable, prefix, workspace)
            names = ("application_app_one", "application_app_two")
            for name, suffix, key in zip(names, ("one", "two"), ("1", "2")):
                package = root / name
                package.mkdir(parents=True, exist_ok=True)
                (package / "__init__.py").write_text(
                    'from qgis_sdk.adapters.desktop import host\nclassFactory = host(__name__ + ".plugin:app")\n',
                    encoding="utf-8",
                )
                (package / "plugin.py").write_text(
                    PLUGIN_SOURCE.replace("NAME", suffix).replace("KEY", key),
                    encoding="utf-8",
                )
                (package / "metadata.txt").write_text(
                    f"[general]\nname=Application {suffix}\ndescription=Application test\nversion=0.1\nqgisMinimumVersion=4.0\nauthor=SDK\nemail=none@example.test\n",
                    encoding="utf-8",
                )
            write_request(
                workspace,
                {
                    "names": list(names),
                    "plugins_root": str(root),
                    "scripts": str(Path(__file__).resolve().parent),
                },
            )
            probe = write_workspace_file(workspace, "app-probe.py", PROBE)
            run_desktop_probe(executable, prefix, workspace, probe)
            report = read_report(workspace)
            if report is None:
                return {"passed": False, "error": "QGIS Desktop wrote no report"}
            return {**report, "passed": passed(report)}
        except Exception as error:  # noqa: BLE001 - a failed qualification is reported
            return {"passed": False, "error": f"{type(error).__name__}: {error}"}


def main() -> int:
    report = run_smoke()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
