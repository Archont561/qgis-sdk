"""Prove plugin coexistence over the optional native runtime in real QGIS Desktop.

TASK-33 AC3 asks for coexistence with another plugin that already uses the same
optional native runtime dependency (``pydantic==2.14.1`` and its native Rust
extension ``pydantic_core``). QGIS plugins share one embedded Python interpreter
and one ``sys.modules`` table inside the Desktop process, so two plugins that
both rely on the native validator must load, validate and unload without module
collisions or cross-plugin state corruption.

This harness installs two fixture plugins into a clean throwaway QGIS Desktop
profile and drives them through ``qgis.utils`` in the real Desktop application:

* ``neighbor_pydantic_probe`` - a conventional QGIS plugin (no ``qgis_sdk``
  dependency) that imports ``pydantic`` and ``pydantic_core`` at startup and
  validates payloads with ``BaseModel``.
* ``sdk_pydantic_probe`` - an SDK plugin bound through
  ``qgis_sdk.adapters.desktop.host()`` (the line ``qgis-sdk build`` stages)
  and ``qgis_sdk.adapters.pydantic.PydanticContractAdapter`` (using
  ``SafeJsonInteger``).

Every stage is confirmed against the live Desktop host:

* ``neighbor_started`` - the neighbor plugin loads and starts first.
* ``pydantic_preloaded`` - ``pydantic`` and ``pydantic_core._pydantic_core`` are
  already loaded in ``sys.modules`` before the SDK plugin starts.
* ``sdk_started`` - the SDK plugin loads and starts alongside the neighbor.
* ``both_loaded`` - ``qgis.utils.isPluginLoaded`` is true for both plugins at
  the same time and the SDK runtime is ``running``.
* ``shared_native_runtime`` - both plugins hold the identical ``pydantic`` and
  ``pydantic_core`` module objects in ``sys.modules``.
* ``sdk_contract_dispatched`` - the SDK plugin validates and serializes a valid
  request through ``PydanticContractAdapter`` and rejects a malformed request
  with ``QgisSdkContractValidationError``.
* ``neighbor_validates_while_coexisting`` - the neighbor plugin still validates
  its own ``BaseModel`` payload while the SDK plugin is active.
* ``sdk_unloaded_cleanly`` - ``unloadPlugin`` stops the SDK plugin and closes
  its ``ResourceScope``.
* ``neighbor_survives_sdk_unload`` - unloading the SDK plugin leaves the
  neighbor plugin loaded and able to validate requests.
* ``neighbor_unloaded_cleanly`` - the neighbor plugin unloads cleanly afterwards.

Run it from the workspace root::

    pixi run -e default python packages/qgis-sdk-python/scripts/plugin_coexistence_smoke.py

Exit codes: 0 = every coexistence stage passed, 1 = a stage failed or QGIS is
unavailable, with the reason recorded in ``error``.
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

NEIGHBOR_PLUGIN: Final = "neighbor_pydantic_probe"
NEIGHBOR_TITLE: Final = "Neighbor Pydantic probe"

SDK_PLUGIN: Final = "sdk_pydantic_probe"
SDK_TITLE: Final = "SDK Pydantic probe"
SDK_ID: Final = "sdk.pydantic.probe"

NEIGHBOR_INIT: Final = '''"""QGIS entry point for the non-SDK neighbor plugin."""

from .plugin import classFactory

__all__ = ["classFactory"]
'''

NEIGHBOR_METADATA: Final = """[general]
name=Neighbor Pydantic probe
description=Conventional QGIS plugin using pydantic directly before the SDK plugin loads.
about=Written by packages/qgis-sdk-python/scripts/plugin_coexistence_smoke.py; never shipped.
version=0.0.0
qgisMinimumVersion=4.0
author=qgis-sdk qualification
email=someone@example.invalid
experimental=True
hasProcessingProvider=No
"""

NEIGHBOR_PLUGIN_SOURCE: Final = '''"""Conventional QGIS plugin that already uses pydantic and pydantic_core."""

from __future__ import annotations

import pydantic
import pydantic_core
from pydantic import BaseModel, ConfigDict


class NeighborPayload(BaseModel):
    """Strict model owned by the non-SDK neighbor plugin."""

    model_config = ConfigDict(strict=True, extra="forbid")

    count: int


class NeighborPydanticPlugin:
    """Minimal QGIS plugin lifecycle holding references to the native runtime."""

    def __init__(self, iface: object) -> None:
        self.iface = iface
        self.pydantic_module = pydantic
        self.pydantic_core_module = pydantic_core._pydantic_core
        self.started = False
        self.unloaded = False

    def initGui(self) -> None:
        self.started = self.validate_json('{"count": 1}') == 1

    def unload(self) -> None:
        self.unloaded = True

    def validate_json(self, raw: str) -> int:
        return NeighborPayload.model_validate_json(raw).count


def classFactory(iface: object) -> NeighborPydanticPlugin:
    return NeighborPydanticPlugin(iface)
'''

SDK_INIT: Final = f'''"""QGIS entry point for the SDK controlled-deployment coexistence fixture.

The one line ``qgis-sdk build`` appends to a staged ``__init__.py``
(decision-43): the runtime's ``host()`` is the ``classFactory``.
"""

from qgis_sdk.adapters.desktop import host

classFactory = host("{SDK_PLUGIN}.plugin:SdkPydanticProbe")
'''

SDK_METADATA: Final = """[general]
name=SDK Pydantic probe
description=SDK plugin using PydanticContractAdapter alongside another Pydantic plugin.
about=Written by packages/qgis-sdk-python/scripts/plugin_coexistence_smoke.py; never shipped.
version=0.0.0
qgisMinimumVersion=4.0
author=qgis-sdk qualification
email=someone@example.invalid
experimental=True
hasProcessingProvider=No
"""

SDK_PLUGIN_SOURCE: Final = f'''"""SDK plugin using PydanticContractAdapter in the shared QGIS interpreter."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pydantic
from pydantic import ConfigDict

from qgis_sdk import action, plugin
from qgis_sdk.adapters.pydantic import PydanticContractAdapter
from qgis_sdk.adapters.pydantic_types import SafeJsonInteger
from qgis_sdk.core import PluginContext, ResourceScope

OBSERVED: dict[str, object] = {{}}


class NoopNotifications:
    """Quiet notifications helper for the coexistence probe."""

    def info(self, message: str) -> None:
        OBSERVED["last_message"] = message


@pydantic.dataclasses.dataclass(
    config=ConfigDict(strict=True, extra="forbid"),
    kw_only=True,
)
class ProbeRequest:
    count: SafeJsonInteger


@pydantic.dataclasses.dataclass(
    config=ConfigDict(strict=True, extra="allow"),
    kw_only=True,
)
class ProbeResultReader:
    processed: SafeJsonInteger


@pydantic.dataclasses.dataclass(
    config=ConfigDict(strict=True, extra="forbid"),
    kw_only=True,
)
class ProbeResultWriter:
    processed: SafeJsonInteger


@dataclass(frozen=True, slots=True)
class IfaceDesktopAccess:
    iface: object


def build_context(iface: object) -> PluginContext:
    return PluginContext(
        notifications=NoopNotifications(),
        scope=ResourceScope(),
        desktop=None if iface is None else IfaceDesktopAccess(iface),
    )


@plugin(id="{SDK_ID}", title="{SDK_TITLE}")
class SdkPydanticProbe:
    """Exercise PydanticContractAdapter inside a live Desktop plugin."""

    ctx: PluginContext
    context_factory = staticmethod(build_context)

    def __init__(self) -> None:
        self.adapter = PydanticContractAdapter(
            request_type=ProbeRequest,
            result_reader_type=ProbeResultReader,
            result_writer_type=ProbeResultWriter,
            handler=lambda request: ProbeResultWriter(processed=request.count),
        )
        OBSERVED["context"] = self.ctx
        OBSERVED["adapter"] = self.adapter
        OBSERVED["pydantic_module"] = pydantic

    @action(id="ping", title="Ping")
    def ping(self, value: int) -> int:
        response = self.adapter.handle_json(json.dumps({{"count": value}}))
        return ProbeResultReader(**json.loads(response)).processed
'''

NEIGHBOR_FILES: Final = {
    "__init__.py": NEIGHBOR_INIT,
    "metadata.txt": NEIGHBOR_METADATA,
    "plugin.py": NEIGHBOR_PLUGIN_SOURCE,
}

SDK_FILES: Final = {
    "__init__.py": SDK_INIT,
    "metadata.txt": SDK_METADATA,
    "plugin.py": SDK_PLUGIN_SOURCE,
}

COEXISTENCE_PROBE: Final = '''"""Assert two-plugin coexistence over pydantic/pydantic_core in QGIS Desktop."""

import importlib
import json
import os
import platform
import sys
from pathlib import Path

workspace = Path(os.environ["QGIS_SDK_DESKTOP_WORKSPACE"])
request = json.loads((workspace / "request.json").read_text(encoding="utf-8"))
neighbor_name = request["neighbor_plugin"]
sdk_name = request["sdk_plugin"]
payload = {
    "platform": platform.platform(),
    "python_version": platform.python_version(),
    "qgis_version": None,
    "pydantic_version": None,
    "pydantic_core_version": None,
    "neighbor_plugin": neighbor_name,
    "sdk_plugin": sdk_name,
    "neighbor_started": False,
    "pydantic_preloaded": False,
    "sdk_started": False,
    "both_loaded": False,
    "shared_native_runtime": False,
    "sdk_contract_dispatched": False,
    "neighbor_validates_while_coexisting": False,
    "action_result": None,
    "sdk_unloaded_cleanly": False,
    "neighbor_survives_sdk_unload": False,
    "neighbor_unloaded_cleanly": False,
    "error": None,
}

EVIDENCE = (
    "neighbor_started",
    "pydantic_preloaded",
    "sdk_started",
    "both_loaded",
    "shared_native_runtime",
    "sdk_contract_dispatched",
    "neighbor_validates_while_coexisting",
    "sdk_unloaded_cleanly",
    "neighbor_survives_sdk_unload",
    "neighbor_unloaded_cleanly",
)


def finish(code: int) -> None:
    with (workspace / "report.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os._exit(code)


def missing() -> list[str]:
    return [key for key in EVIDENCE if payload[key] is not True]


try:
    import qgis.utils
    from qgis.core import Qgis
    from qgis_sdk.models import QgisSdkContractValidationError

    payload["qgis_version"] = Qgis.QGIS_VERSION
    if qgis.utils.iface is None:
        payload["error"] = "QGIS provided no interface object, so there is nothing to qualify"
        finish(1)

    payload["neighbor_started"] = bool(
        qgis.utils.loadPlugin(neighbor_name)
        and qgis.utils.startPlugin(neighbor_name)
        and qgis.utils.isPluginLoaded(neighbor_name)
    )
    if not payload["neighbor_started"]:
        payload["error"] = "QGIS could not start the neighbor Pydantic plugin"
        finish(1)

    pydantic_before = sys.modules.get("pydantic")
    core_before = sys.modules.get("pydantic_core._pydantic_core")
    payload["pydantic_preloaded"] = (
        pydantic_before is not None and core_before is not None
    )
    if pydantic_before is not None:
        payload["pydantic_version"] = getattr(pydantic_before, "__version__", None)
    pydantic_core_pkg = sys.modules.get("pydantic_core")
    if pydantic_core_pkg is not None:
        payload["pydantic_core_version"] = getattr(
            pydantic_core_pkg, "__version__", None
        )

    payload["sdk_started"] = bool(
        qgis.utils.loadPlugin(sdk_name)
        and qgis.utils.startPlugin(sdk_name)
        and qgis.utils.isPluginLoaded(sdk_name)
    )
    if not payload["sdk_started"]:
        payload["error"] = "QGIS could not start the SDK Pydantic plugin"
        finish(1)

    neighbor_instance = qgis.utils.plugins[neighbor_name]
    sdk_adapter = qgis.utils.plugins[sdk_name]
    payload["both_loaded"] = bool(
        qgis.utils.isPluginLoaded(neighbor_name)
        and qgis.utils.isPluginLoaded(sdk_name)
        and neighbor_instance.started
        and sdk_adapter.runtime.state.value == "running"
    )

    sdk_module = importlib.import_module(sdk_name + ".plugin")
    payload["shared_native_runtime"] = bool(
        neighbor_instance.pydantic_module is pydantic_before
        and sdk_module.OBSERVED["pydantic_module"] is pydantic_before
        and neighbor_instance.pydantic_core_module is core_before
        and sys.modules.get("pydantic_core._pydantic_core") is core_before
    )

    ping_value = request["ping_value"]
    payload["action_result"] = sdk_adapter.runtime.actions["ping"](ping_value)
    contract_adapter = sdk_module.OBSERVED["adapter"]
    rejected_invalid = False
    try:
        contract_adapter.handle_json('{"count": "not-an-int"}')
    except QgisSdkContractValidationError as validation_error:
        rejected_invalid = validation_error.code == "contract_validation_failed"
    payload["sdk_contract_dispatched"] = (
        payload["action_result"] == ping_value and rejected_invalid
    )

    payload["neighbor_validates_while_coexisting"] = (
        neighbor_instance.validate_json(json.dumps({"count": ping_value}))
        == ping_value
    )

    sdk_context = sdk_module.OBSERVED["context"]
    payload["sdk_unloaded_cleanly"] = bool(
        qgis.utils.unloadPlugin(sdk_name)
        and not qgis.utils.isPluginLoaded(sdk_name)
        and sdk_adapter.runtime.state.value == "stopped"
        and sdk_context.scope.closed
    )

    payload["neighbor_survives_sdk_unload"] = bool(
        qgis.utils.isPluginLoaded(neighbor_name)
        and not neighbor_instance.unloaded
        and neighbor_instance.validate_json(json.dumps({"count": ping_value}))
        == ping_value
    )

    payload["neighbor_unloaded_cleanly"] = bool(
        qgis.utils.unloadPlugin(neighbor_name)
        and not qgis.utils.isPluginLoaded(neighbor_name)
        and neighbor_instance.unloaded
    )
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
    "pydantic_version",
    "pydantic_core_version",
    "neighbor_plugin",
    "sdk_plugin",
    "neighbor_started",
    "pydantic_preloaded",
    "sdk_started",
    "both_loaded",
    "shared_native_runtime",
    "sdk_contract_dispatched",
    "neighbor_validates_while_coexisting",
    "action_result",
    "sdk_unloaded_cleanly",
    "neighbor_survives_sdk_unload",
    "neighbor_unloaded_cleanly",
    "error",
)

EVIDENCE_FIELDS: Final = (
    "neighbor_started",
    "pydantic_preloaded",
    "sdk_started",
    "both_loaded",
    "shared_native_runtime",
    "sdk_contract_dispatched",
    "neighbor_validates_while_coexisting",
    "sdk_unloaded_cleanly",
    "neighbor_survives_sdk_unload",
    "neighbor_unloaded_cleanly",
)


@dataclass(frozen=True)
class PluginCoexistenceReport:
    """What a real QGIS Desktop run observed for two plugins sharing Pydantic."""

    platform: str
    python_version: str
    qgis_version: str | None
    pydantic_version: str | None
    pydantic_core_version: str | None
    neighbor_plugin: str
    sdk_plugin: str
    neighbor_started: bool
    pydantic_preloaded: bool
    sdk_started: bool
    both_loaded: bool
    shared_native_runtime: bool
    sdk_contract_dispatched: bool
    neighbor_validates_while_coexisting: bool
    action_result: int | None
    sdk_unloaded_cleanly: bool
    neighbor_survives_sdk_unload: bool
    neighbor_unloaded_cleanly: bool
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether every coexistence stage was confirmed by the live host."""
        confirmed = all(getattr(self, name) for name in EVIDENCE_FIELDS)
        return confirmed and self.action_result == PING_VALUE

    @classmethod
    def unavailable(cls, error: str | None = None) -> PluginCoexistenceReport:
        """Return the report for a run that could observe nothing."""
        return cls(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            pydantic_version=None,
            pydantic_core_version=None,
            neighbor_plugin=NEIGHBOR_PLUGIN,
            sdk_plugin=SDK_PLUGIN,
            neighbor_started=False,
            pydantic_preloaded=False,
            sdk_started=False,
            both_loaded=False,
            shared_native_runtime=False,
            sdk_contract_dispatched=False,
            neighbor_validates_while_coexisting=False,
            action_result=None,
            sdk_unloaded_cleanly=False,
            neighbor_survives_sdk_unload=False,
            neighbor_unloaded_cleanly=False,
            error=error,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> PluginCoexistenceReport:
        """Build a report from a probe's JSON, ignoring anything unexpected."""
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in known})

    def to_payload(self) -> dict[str, object]:
        """Return the report as JSON-compatible data, including the verdict."""
        return {**asdict(self), "passed": self.passed}


def request_document(plugins_root: Path) -> str:
    """Return the probe's sidecar: plugin names, path and ping value."""
    return json.dumps(
        {
            "neighbor_plugin": NEIGHBOR_PLUGIN,
            "sdk_plugin": SDK_PLUGIN,
            "plugins_root": str(plugins_root),
            "ping_value": PING_VALUE,
        }
    )


def _write_package(plugins_root: Path, name: str, files: dict[str, str]) -> Path:
    package = plugins_root / name
    package.mkdir(parents=True, exist_ok=True)
    for filename, text in sorted(files.items()):
        (package / filename).write_text(text, encoding="utf-8", newline="\n")
    return package


def install_fixtures(plugins_root: Path) -> tuple[Path, Path]:
    """Write both fixture plugin packages into the profile's plugin directory."""
    return (
        _write_package(plugins_root, NEIGHBOR_PLUGIN, NEIGHBOR_FILES),
        _write_package(plugins_root, SDK_PLUGIN, SDK_FILES),
    )


def _run_coexistence(
    executable: Path, prefix: Path, workspace: Path
) -> PluginCoexistenceReport:
    """Install both fixtures, then drive the coexistence sequence in Desktop."""
    ensure_source_root_on_path()
    plugins_root = profile_plugin_dir(executable, prefix, workspace)
    install_fixtures(plugins_root)

    write_workspace_file(workspace, REQUEST_FILE, request_document(plugins_root))
    probe = write_workspace_file(workspace, "coexistence-probe.py", COEXISTENCE_PROBE)
    run_desktop_probe(executable, prefix, workspace, probe)

    payload = read_report(workspace)
    if payload is None:
        return PluginCoexistenceReport.unavailable(
            f"the Desktop probe wrote no {REPORT_FILE}"
        )
    return PluginCoexistenceReport.from_payload(payload)


def run_smoke(prefix: Path | None = None) -> PluginCoexistenceReport:
    """Drive one real-Desktop plugin coexistence cycle, or record why it failed."""
    prefix = prefix or Path(sys.prefix)
    executable = qgis_executable(prefix)
    if not executable.is_file():
        return PluginCoexistenceReport.unavailable(
            f"QGIS Desktop executable not found: {executable}"
        )
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-coexistence-"))
    try:
        return _run_coexistence(executable, prefix, workspace)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return PluginCoexistenceReport.unavailable(f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    """Print the report and exit non-zero when the host did not confirm everything."""
    parser = argparse.ArgumentParser(
        description="Prove plugin coexistence over Pydantic in real QGIS Desktop (headless)."
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
