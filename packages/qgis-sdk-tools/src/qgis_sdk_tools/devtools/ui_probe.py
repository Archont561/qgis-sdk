"""Capture and drive a plugin's own surfaces inside a QGIS process (decision-51).

``qgis-sdk ui`` cannot touch a widget from the CLI process: the surfaces are Qt
objects that only exist where the plugin runs. So the command writes a request,
this module executes it inside a QGIS interpreter - headless ``QgsApplication``
is enough, because the plugin is started through the generated ``classFactory``
with ``iface=None`` - and the report it writes is what the command prints.

Everything here is developer tooling by construction: driving a surface with
synthetic input needs ``QtTest``, and the runtime a plugin ZIP vendors never
imports it.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

__all__ = [
    "PROBE_ENTRYPOINT",
    "REQUEST_ENV",
    "ActStep",
    "CaptureRequest",
    "main",
    "perform",
    "run",
]

REQUEST_ENV: Final = "QGIS_SDK_UI_REQUEST"
"""Where the probe finds the request JSON the command wrote."""

PROBE_ENTRYPOINT: Final = "qgis_sdk_tools.devtools.ui_probe"
"""The module a QGIS interpreter runs; ``-m`` gives it ``main``."""

#: Verbs ``dev.ui.act`` offers, and the widget kinds each one accepts.
VERBS: Final = ("click", "focus", "select", "set", "type")


@dataclass(frozen=True, slots=True)
class ActStep:
    """One synthetic interaction with the surface, by node id."""

    node: str
    verb: str
    value: object = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ActStep:
        verb = str(payload.get("verb", ""))
        if verb not in VERBS:
            raise ValueError(f"unknown verb {verb!r}; choose {', '.join(VERBS)}")
        return cls(node=str(payload["node"]), verb=verb, value=payload.get("value"))


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    """What the CLI asks a QGIS process to do, and where to leave the answer."""

    project: Path
    plugin: str
    surface: str
    out: Path
    screenshot: bool = True
    steps: tuple[ActStep, ...] = ()
    report: Path | None = None
    open_only: bool = False
    """Open the surface and describe it, without writing a capture."""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CaptureRequest:
        report = payload.get("report")
        return cls(
            project=Path(str(payload["project"])),
            plugin=str(payload["plugin"]),
            surface=str(payload["surface"]),
            out=Path(str(payload["out"])),
            screenshot=bool(payload.get("screenshot", True)),
            steps=tuple(
                ActStep.from_mapping(step) for step in payload.get("steps") or ()
            ),
            report=None if report is None else Path(str(report)),
            open_only=bool(payload.get("open_only", False)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "project": str(self.project),
            "plugin": self.plugin,
            "surface": self.surface,
            "out": str(self.out),
            "screenshot": self.screenshot,
            "steps": [
                {"node": step.node, "verb": step.verb, "value": step.value}
                for step in self.steps
            ],
            "report": None if self.report is None else str(self.report),
            "open_only": self.open_only,
        }


@dataclass
class CaptureReport:
    """What happened: the surfaces found, the steps applied and the captures."""

    ok: bool = False
    plugin: str = ""
    surfaces: list[dict[str, Any]] = field(default_factory=list)
    surface: str | None = None
    opened: dict[str, Any] | None = None
    """What ``open`` found, when the request asked only to open."""
    steps: list[dict[str, Any]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "plugin": self.plugin,
            "surfaces": self.surfaces,
            "surface": self.surface,
            "opened": self.opened,
            "steps": self.steps,
            "files": self.files,
            "error": self.error,
        }


def run(request: CaptureRequest) -> CaptureReport:
    """Execute ``request`` in this process; needs a running QGIS application.

    The plugin starts through the generated ``classFactory`` - the same entry
    point ``qgis-sdk build`` writes - so a capture exercises the real host,
    and only the surfaces the host owns can be reached.
    """
    report = CaptureReport(plugin=request.plugin)
    try:
        _run(request, report)
    except BaseException:  # noqa: BLE001 - the report carries the failure
        report.ok = False
        report.error = traceback.format_exc()
    return report


def main() -> int:
    """Probe entry point: read the request, write the report, exit on its verdict."""
    path = os.environ.get(REQUEST_ENV)
    if not path:
        print(f"{PROBE_ENTRYPOINT}: {REQUEST_ENV} is not set", file=sys.stderr)
        return 2
    request = CaptureRequest.from_mapping(json.loads(Path(path).read_text("utf-8")))
    report = run(request)
    payload = report.to_mapping()
    if request.report is None:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        request.report.parent.mkdir(parents=True, exist_ok=True)
        request.report.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0 if report.ok else 1


def _run(request: CaptureRequest, report: CaptureReport) -> None:
    sys.path.insert(0, str(request.project))
    from qgis_sdk.adapters.desktop import host, resolve_plugin_spec
    from qgis_sdk.ui.surfaces import describe_surface

    spec = f"{request.plugin}.plugin:app"
    application = resolve_plugin_spec(spec)
    surfaces = tuple(getattr(application, "surfaces", ()) or ())
    report.surfaces = [
        {
            "id": describe_surface(surface).id,
            "kind": describe_surface(surface).kind,
            "title": describe_surface(surface).title,
        }
        for surface in surfaces
    ]
    if request.surface != "-":
        chosen = [
            surface
            for surface in surfaces
            if describe_surface(surface).id == request.surface
        ]
        if not chosen:
            known = ", ".join(entry["id"] for entry in report.surfaces) or "none"
            raise LookupError(
                f"{request.plugin} declares no surface named {request.surface!r} "
                f"(declared: {known})"
            )
        _capture(host(spec), chosen[0], request, report)
        return
    report.ok = True  # listing asks a question and writes nothing


def _capture(
    factory: Any, surface: type, request: CaptureRequest, report: CaptureReport
) -> None:
    from qgis_sdk.ui.surfaces import describe_surface

    description = describe_surface(surface)
    report.surface = description.id
    plugin = factory(None)
    plugin.initGui()
    try:
        surfaces = plugin.surfaces
        if surfaces is None:  # pragma: no cover - a host without UI cannot be asked
            raise RuntimeError("this host exposes no surfaces")
        surfaces.open(surface)
        if request.open_only:
            _describe_open(surfaces, description, report)
            return
        before = surfaces.snapshot(description.id, screenshot=request.screenshot)[0]
        report.files.update(_write(before, request.out, f"{description.id}-before"))
        if request.steps:
            _perform(surfaces, description.id, request.steps, report)
        after = surfaces.snapshot(description.id, screenshot=request.screenshot)[0]
        report.files.update(_write(after, request.out, description.id))
        report.ok = True
    finally:
        plugin.unload()


def _describe_open(surfaces: Any, description: Any, report: CaptureReport) -> None:
    """Report the window an ``open`` produced: no file, just what is on screen."""
    widget = _dialog_widget(surfaces, description.id)
    tree = surfaces.snapshot(description.id, screenshot=False)[0].tree
    report.opened = {
        "surface": description.id,
        "kind": description.kind,
        "title": description.title,
        "widget": type(widget).__name__,
        "size": tree.get("size"),
        "nodes": _count(tree.get("nodes") or ()),
        "findings": [entry.get("code") for entry in tree.get("findings") or ()],
    }
    report.ok = True


def _count(nodes: Any) -> int:
    """How many nodes a snapshot tree holds, children included."""
    return sum(1 + _count(node.get("children") or ()) for node in nodes)


def _perform(
    surfaces: Any,
    surface_id: str,
    steps: Sequence[ActStep],
    report: CaptureReport,
) -> None:
    from qgis.PyQt.QtCore import QCoreApplication

    widget = _dialog_widget(surfaces, surface_id)
    for step in steps:
        target = widget.findChild(_qwidget(), step.node)
        if target is None:
            raise LookupError(
                f"{surface_id} has no widget named {step.node!r} to {step.verb}"
            )
        outcome = perform(target, step)
        QCoreApplication.processEvents()
        report.steps.append(
            {"node": step.node, "verb": step.verb, "value": step.value, **outcome}
        )


def perform(target: Any, step: ActStep) -> dict[str, Any]:
    """Apply one step through ``QTest``/Qt and report what the widget then holds.

    Synthetic input, not a direct setter, is what proves the wiring: a form
    that only looks right when a test pokes its model is not the form a user
    drives, so clicks and typing go through the same event path a user's do.
    """
    from qgis.PyQt.QtCore import QCoreApplication, Qt
    from qgis.PyQt.QtTest import QTest

    if step.verb == "click":
        QTest.mouseClick(target, Qt.MouseButton.LeftButton)
    elif step.verb == "focus":
        target.setFocus()
        QCoreApplication.processEvents()
    elif step.verb == "type":
        QTest.keyClicks(target, str(step.value if step.value is not None else ""))
    elif step.verb == "set":
        _clear(target)
        QTest.keyClicks(target, _as_text(step.value))
    elif step.verb == "select":
        _select(target, step.value)
    QCoreApplication.processEvents()
    return {"value": _read(target)}


def _clear(target: Any) -> None:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtTest import QTest

    select_all = getattr(target, "selectAll", None)
    if callable(select_all):
        select_all()
        QTest.keyClick(target, Qt.Key.Key_Delete)


def _select(target: Any, value: object) -> None:
    setter = getattr(target, "setCurrentText", None)
    if not callable(setter):
        raise TypeError(
            f"{type(target).__name__} has no selectable text; use set or click"
        )
    setter(str(value))


def _read(target: Any) -> Any:
    for name in ("value", "text", "currentText", "isChecked"):
        reader = getattr(target, name, None)
        if not callable(reader):
            continue
        try:
            return reader()
        except TypeError:
            continue
    return None


def _as_text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def _qwidget() -> Any:
    from qgis.PyQt.QtWidgets import QWidget

    return QWidget


def _dialog_widget(surfaces: Any, surface_id: str) -> Any:
    """The window of ``surface_id``, reached through the host that opened it."""
    from qgis_sdk.ui.surfaces import describe_surface

    for dialog in surfaces.dialogs:
        if describe_surface(type(dialog.surface)).id == surface_id:
            return dialog.widget
    for dock in surfaces.docks.values():
        if describe_surface(type(dock.surface)).id == surface_id:
            return dock.widget
    raise LookupError(f"{surface_id} is not open, so it cannot be driven")


def _write(capture: Any, out: Path, stem: str) -> dict[str, str]:
    json_path, png_path = capture.write(out / stem)
    written = {"json": str(json_path)}
    if png_path is not None:
        written["png"] = str(png_path)
    return written
