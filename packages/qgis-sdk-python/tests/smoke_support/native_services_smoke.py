"""Repeatable headless harness for the native layer and project services.

This helper starts a real QGIS application, drives ``NativeLayers`` and
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

Run its pytest smoke test with ``pytest -m smoke``.

The report helpers are pure, so the QGIS-free suite tests them; the end-to-end
run is opt-in through the test suite.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from smoke_support.desktop_lifecycle_smoke import headless_environment, qgis_python_path


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_run_services_p1(_s):
    from PyQt6.QtCore import QT_VERSION_STR

    _s.QT_VERSION_STR = QT_VERSION_STR
    from qgis.core import Qgis, QgsApplication, QgsProject, QgsSettings

    _s.Qgis = Qgis
    _s.QgsApplication = QgsApplication
    _s.QgsProject = QgsProject
    _s.QgsSettings = QgsSettings

    _s.QgsApplication.setPrefixPath(str(_s.prefix), True)
    _s.application = _s.QgsApplication([b"qgis-sdk-native-services-smoke"], True)
    _s.application.initQgis()


def _cc_run_services_p2(_s):

    from qgis_sdk.adapters.qgis import (
        NativeLayers,
        NativeNotifications,
        NativeProject,
        NativeSettings,
        NativeStyles,
    )

    _s.NativeLayers = NativeLayers
    _s.NativeNotifications = NativeNotifications
    _s.NativeProject = NativeProject
    _s.NativeSettings = NativeSettings
    _s.NativeStyles = NativeStyles
    from qgis_sdk.core import ResourceScope

    _s.ResourceScope = ResourceScope
    from qgis_sdk.models import QgisSdkScopeClosedError, QgisSdkStyleIncompatibleError

    _s.QgisSdkScopeClosedError = QgisSdkScopeClosedError
    _s.QgisSdkStyleIncompatibleError = QgisSdkStyleIncompatibleError

    _s.QgsProject.instance().removeAllMapLayers()


def _cc_run_services_p3(_s):
    _s.scope = _s.ResourceScope()
    _s.layers = _s.NativeLayers(_s.scope)
    _s.project = _s.NativeProject(_s.layers, _s.scope)
    _s.settings = _s.NativeSettings(_s.scope, prefix=SETTINGS_PREFIX)
    _s.styles = _s.NativeStyles(_s.layers, _s.scope)
    _s.delivered: list[tuple[str, str]] = []
    _s.notifications = _s.NativeNotifications(
        _s.scope, sink=lambda n: _s.delivered.append((n.level, n.message))
    )


def _cc_run_services_p4(_s):
    # The default sink writes to the QGIS message log, which QGIS swallows from
    # Python's stdout, so this run proves it executes at every level without
    # raising rather than claiming to read the log back.
    _s.log = _s.NativeNotifications(_s.scope)
    _s.log.info("default message-log sink")
    _s.log.with_action("Retry", "retry").warning("default message-log sink, levelled")

    _s.info = _s.layers.open_vector(FIXTURE_DATASET)
    _s.project.add_layer(_s.info.id)
    # A selection is a host action; the contract only reads one (decision-19).
    _s.QgsProject.instance().mapLayer(_s.info.id).selectByIds(list(SELECTED_FEATURES))
    _s.selection = tuple(sorted(_s.layers.selection(_s.info.id)))


def _cc_run_services_p5(_s):
    _s.project_layer_ids = _s.project.layer_ids()

    _s.theme_before = _theme_snapshot()
    _s.styles.apply_style(_s.info.id, COMPATIBLE_STYLE)
    _s.renderer = _s.QgsProject.instance().mapLayer(_s.info.id).renderer()
    _s.style_applied = _s.renderer is not None and _s.renderer.type() == "singleSymbol"
    try:
        _s.styles.apply_style(_s.info.id, INCOMPATIBLE_STYLE)
    except _s.QgisSdkStyleIncompatibleError:
        _s.style_refused = True
    else:
        _s.style_refused = False


def _cc_run_services_p6(_s):
    _s.theme_unchanged = _theme_snapshot() == _s.theme_before

    _s.settings.set(SETTINGS_KEY, SETTINGS_VALUE)
    _s.settings_round_trip = _s.settings.get(SETTINGS_KEY) == SETTINGS_VALUE
    _s.notifications.info(NOTIFICATION)
    _s.notifications.success(NOTIFICATION)
    _s.notification_delivered = _s.delivered == [
        ("info", NOTIFICATION),
        ("success", NOTIFICATION),
    ]

    _s.scope.close()


def _cc_run_services_p7(_s):
    try:
        _s.layers.list_layers()
    except _s.QgisSdkScopeClosedError:
        _s.refused = True
    else:
        _s.refused = False
    try:
        _s.settings.set(SETTINGS_KEY, "after-close")
    except _s.QgisSdkScopeClosedError:
        _s.settings_refused = True
    else:
        _s.settings_refused = False


def _cc_run_services_p8(_s):
    try:
        _s.notifications.info("after-close")
    except _s.QgisSdkScopeClosedError:
        _s.notification_refused = True
    else:
        _s.notification_refused = False
    _s.scope.close()  # repeated close must stay a no-op

    _s.QgsSettings().remove(SETTINGS_PREFIX)
    _s.QgsProject.instance().removeAllMapLayers()
    _s.application.exitQgis()


def _cc_run_services_p9(_s):

    return _CcReturn(
        NativeServicesReport(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=_s.Qgis.QGIS_VERSION,
            qt_version=_s.QT_VERSION_STR,
            qgis_initialised=True,
            layer_opened=True,
            layer_name=_s.info.name,
            layer_geometry_type=_s.info.geometry_type,
            layer_field_names=_s.info.field_names,
            layer_crs=_s.info.crs,
            selection=_s.selection,
            project_layer_ids=_s.project_layer_ids,
            scope_closed=_s.scope.closed,
            reads_refused_after_close=_s.refused,
            settings_round_trip=_s.settings_round_trip,
            settings_refused_after_close=_s.settings_refused,
            notification_delivered=_s.notification_delivered,
            notification_refused_after_close=_s.notification_refused,
            style_applied=_s.style_applied,
            style_incompatible_refused=_s.style_refused,
            theme_unchanged=_s.theme_unchanged,
            qgis_exited=True,
        )
    )


def _unavailable_facts1(cls, error):
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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The runtime and the tools are separate distributions (decision-35); both go
# on the path so the probe imports the trees under test.
SOURCE_ROOTS = (
    PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src",
    PROJECT_ROOT.parent / "qgis-sdk-tools" / "src",
)
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
        return all(
            (
                self.qgis_initialised,
                self.layer_opened,
                self.layer_name == EXPECTED_NAME,
                self.layer_geometry_type == EXPECTED_GEOMETRY,
                self.layer_field_names == EXPECTED_FIELDS,
                self.layer_crs == EXPECTED_CRS,
                self.selection == SELECTED_FEATURES,
                len(self.project_layer_ids) == 1,
                self.scope_closed,
                self.reads_refused_after_close,
                self.settings_round_trip,
                self.settings_refused_after_close,
                self.notification_delivered,
                self.notification_refused_after_close,
                self.style_applied,
                self.style_incompatible_refused,
                self.theme_unchanged,
                self.qgis_exited,
            )
        )

    @classmethod
    def unavailable(cls, error: str | None = None) -> NativeServicesReport:
        """Return the report for a host where nothing could run.

        Every stage is false and no version is known. The harness answers with
        this instead of raising, so a broken environment still produces a
        machine-readable report - and one place decides what "did not get that
        far" looks like.
        """
        return _unavailable_facts1(cls, error)

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
    for root in reversed(SOURCE_ROOTS):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

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
    _s = _CcState(prefix=prefix)
    for _p in (
        _cc_run_services_p1,
        _cc_run_services_p2,
        _cc_run_services_p3,
        _cc_run_services_p4,
        _cc_run_services_p5,
        _cc_run_services_p6,
        _cc_run_services_p7,
        _cc_run_services_p8,
        _cc_run_services_p9,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
