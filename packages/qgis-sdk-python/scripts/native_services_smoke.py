"""Repeatable headless harness for the native layer and project services.

This script starts a real QGIS application, drives ``NativeLayers`` and
``NativeProject`` against the reference fixture dataset, proves that a selection
made through QGIS is readable through the contract, and proves that closing the
owner scope releases the layers and refuses further work. It prints a
machine-readable report.

It covers the layer/project services, the scoped settings service and the
notification contract (TASK-25.3), and packaged style application with the
application theme proven unchanged across it (TASK-25.4).

It is **not** a Desktop GUI qualification: there is no display, no canvas and no
widget in this sandbox, and no Windows or macOS claim comes from it. Those remain
TASK-33.

Run it from the workspace root with the default Pixi environment::

    pixi run -e default python packages/qgis-sdk-python/scripts/native_services_smoke.py
    # or name a candidate root explicitly, e.g. on a Windows/macOS host
    pixi run -e default python packages/qgis-sdk-python/scripts/native_services_smoke.py --prefix /opt/qgis

The report helpers are pure, so the QGIS-free suite tests them; the end-to-end
run is opt-in through the test suite.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from desktop_lifecycle_smoke import headless_environment, qgis_python_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
FIXTURE_DATASET = PROJECT_ROOT / "tests" / "fixtures" / "reference" / "points.geojson"
EXPECTED_NAME = "points"
EXPECTED_GEOMETRY = "point"
EXPECTED_CRS = "EPSG:4326"
EXPECTED_FIELDS = ("id", "value")
SELECTED_FEATURES = (1, 3)
SETTINGS_KEY = "reference/distance-unit"
SETTINGS_VALUE = "metres"
NOTIFICATION = "reference workflow opened"
# One fixed prefix keeps repeated runs from accumulating keys in the profile.
SETTINGS_PREFIX = "qgis-sdk/native-services-smoke"
COMPATIBLE_STYLE = "reference/point-output"
INCOMPATIBLE_STYLE = "reference/line-output"
THEME_ROLES = (
    "Window",
    "WindowText",
    "Base",
    "Text",
    "Button",
    "Highlight",
)


@dataclass(frozen=True)
class NativeServicesReport:
    """What one headless run of the native services observed."""

    platform: str
    python_version: str
    qgis_version: str | None
    qt_version: str | None
    qgis_initialised: bool
    layer_opened: bool
    layer_name: str | None
    layer_geometry_type: str | None
    layer_field_names: tuple[str, ...]
    layer_crs: str | None
    selection: tuple[int, ...]
    project_layer_ids: tuple[str, ...]
    scope_closed: bool
    reads_refused_after_close: bool
    settings_round_trip: bool
    settings_refused_after_close: bool
    notification_delivered: bool
    notification_refused_after_close: bool
    style_applied: bool
    style_incompatible_refused: bool
    theme_unchanged: bool
    qgis_exited: bool
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether every native service stage produced its expected value."""
        return (
            self.qgis_initialised
            and self.layer_opened
            and self.layer_name == EXPECTED_NAME
            and self.layer_geometry_type == EXPECTED_GEOMETRY
            and self.layer_field_names == EXPECTED_FIELDS
            and self.layer_crs == EXPECTED_CRS
            and self.selection == SELECTED_FEATURES
            and len(self.project_layer_ids) == 1
            and self.scope_closed
            and self.reads_refused_after_close
            and self.settings_round_trip
            and self.settings_refused_after_close
            and self.notification_delivered
            and self.notification_refused_after_close
            and self.style_applied
            and self.style_incompatible_refused
            and self.theme_unchanged
            and self.qgis_exited
        )

    @classmethod
    def unavailable(cls, error: str | None = None) -> NativeServicesReport:
        """Return the report for a host where nothing could run.

        Every stage is false and no version is known. The harness answers with
        this instead of raising, so a broken environment still produces a
        machine-readable report - and one place decides what "did not get that
        far" looks like.
        """
        return cls(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            qt_version=None,
            qgis_initialised=False,
            layer_opened=False,
            layer_name=None,
            layer_geometry_type=None,
            layer_field_names=(),
            layer_crs=None,
            selection=(),
            project_layer_ids=(),
            scope_closed=False,
            reads_refused_after_close=False,
            settings_round_trip=False,
            settings_refused_after_close=False,
            notification_delivered=False,
            notification_refused_after_close=False,
            style_applied=False,
            style_incompatible_refused=False,
            theme_unchanged=False,
            qgis_exited=False,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable mapping."""
        payload = asdict(self)
        payload["layer_field_names"] = list(self.layer_field_names)
        payload["selection"] = list(self.selection)
        payload["project_layer_ids"] = list(self.project_layer_ids)
        payload["passed"] = self.passed
        return payload


def run_smoke(prefix: Path | None = None) -> NativeServicesReport:
    """Start QGIS, drive the native services and report what happened."""
    prefix = prefix or Path(sys.prefix)
    for key, value in headless_environment(prefix, os.environ).items():
        os.environ[key] = value
    bindings = str(qgis_python_path(prefix))
    if bindings not in sys.path:
        sys.path.insert(0, bindings)
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))

    failed = NativeServicesReport.unavailable()
    try:
        return _run_services(prefix)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return replace(failed, error=f"{type(error).__name__}: {error}")


def _theme_snapshot() -> tuple[object, ...]:
    """Read the application stylesheet and the palette roles a theme paints with."""
    from PyQt6.QtWidgets import QApplication

    application = QApplication.instance()
    palette = application.palette()
    colours = tuple(
        palette.color(getattr(palette.ColorRole, role)).name() for role in THEME_ROLES
    )
    return (application.styleSheet(), colours)


def _run_services(prefix: Path) -> NativeServicesReport:
    """Drive one native services run inside a real headless QgsApplication."""
    from PyQt6.QtCore import QT_VERSION_STR
    from qgis.core import Qgis, QgsApplication, QgsProject, QgsSettings

    QgsApplication.setPrefixPath(str(prefix), True)
    application = QgsApplication([b"qgis-sdk-native-services-smoke"], True)
    application.initQgis()

    from qgis_sdk.adapters.qgis import (
        NativeLayers,
        NativeNotifications,
        NativeProject,
        NativeSettings,
        NativeStyles,
    )
    from qgis_sdk.core import ResourceScope
    from qgis_sdk.models import QgisSdkScopeClosedError, QgisSdkStyleIncompatibleError

    QgsProject.instance().removeAllMapLayers()
    scope = ResourceScope()
    layers = NativeLayers(scope)
    project = NativeProject(layers, scope)
    settings = NativeSettings(scope, prefix=SETTINGS_PREFIX)
    styles = NativeStyles(layers, scope)
    delivered: list[str] = []
    notifications = NativeNotifications(scope, sink=delivered.append)
    # The default sink writes to the QGIS message log, which QGIS swallows from
    # Python's stdout, so this run proves it executes without raising rather than
    # claiming to read the log back.
    NativeNotifications(scope).info("default message-log sink")

    info = layers.open_vector(FIXTURE_DATASET)
    project.add_layer(info.id)
    # A selection is a host action; the contract only reads one (decision-19).
    QgsProject.instance().mapLayer(info.id).selectByIds(list(SELECTED_FEATURES))
    selection = tuple(sorted(layers.selection(info.id)))
    project_layer_ids = project.layer_ids()

    theme_before = _theme_snapshot()
    styles.apply_style(info.id, COMPATIBLE_STYLE)
    renderer = QgsProject.instance().mapLayer(info.id).renderer()
    style_applied = renderer is not None and renderer.type() == "singleSymbol"
    try:
        styles.apply_style(info.id, INCOMPATIBLE_STYLE)
    except QgisSdkStyleIncompatibleError:
        style_refused = True
    else:
        style_refused = False
    theme_unchanged = _theme_snapshot() == theme_before

    settings.set(SETTINGS_KEY, SETTINGS_VALUE)
    settings_round_trip = settings.get(SETTINGS_KEY) == SETTINGS_VALUE
    notifications.info(NOTIFICATION)
    notification_delivered = delivered == [NOTIFICATION]

    scope.close()
    try:
        layers.list_layers()
    except QgisSdkScopeClosedError:
        refused = True
    else:
        refused = False
    try:
        settings.set(SETTINGS_KEY, "after-close")
    except QgisSdkScopeClosedError:
        settings_refused = True
    else:
        settings_refused = False
    try:
        notifications.info("after-close")
    except QgisSdkScopeClosedError:
        notification_refused = True
    else:
        notification_refused = False
    scope.close()  # repeated close must stay a no-op

    QgsSettings().remove(SETTINGS_PREFIX)
    QgsProject.instance().removeAllMapLayers()
    application.exitQgis()

    return NativeServicesReport(
        platform=platform.platform(),
        python_version=platform.python_version(),
        qgis_version=Qgis.QGIS_VERSION,
        qt_version=QT_VERSION_STR,
        qgis_initialised=True,
        layer_opened=True,
        layer_name=info.name,
        layer_geometry_type=info.geometry_type,
        layer_field_names=info.field_names,
        layer_crs=info.crs,
        selection=selection,
        project_layer_ids=project_layer_ids,
        scope_closed=scope.closed,
        reads_refused_after_close=refused,
        settings_round_trip=settings_round_trip,
        settings_refused_after_close=settings_refused,
        notification_delivered=notification_delivered,
        notification_refused_after_close=notification_refused,
        style_applied=style_applied,
        style_incompatible_refused=style_refused,
        theme_unchanged=theme_unchanged,
        qgis_exited=True,
    )


def parse_prefix(arguments: Sequence[str]) -> Path | None:
    """Read an optional ``--prefix`` so a candidate root can be named explicitly."""
    for index, argument in enumerate(arguments):
        if argument == "--prefix" and index + 1 < len(arguments):
            return Path(arguments[index + 1])
        if argument.startswith("--prefix="):
            return Path(argument.split("=", 1)[1])
    return None


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the harness and print its JSON report.

    A host that cannot run the services still exits with a serialisable report and
    a non-zero status, which is what the QGIS-free test asserts.
    """
    report = run_smoke(parse_prefix(sys.argv[1:] if arguments is None else arguments))
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
