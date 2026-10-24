"""One contract suite, one entry per service backend.

TASK-25.1 requires the native adapter to be held to these same tests rather than
to a parallel suite, so a backend joins by adding a factory to ``BACKENDS`` and
every contract test then runs against it unchanged. Fake/native parity is
therefore a property of the test run, not a claim in a review.

The ``native`` backend is registered only when ``QGIS_SDK_NATIVE_SERVICES=1`` and
the QGIS Python bindings of the active prefix exist, so the ordinary QGIS-free
run stays pure and the opt-in run exercises real QGIS. It is a *partial* native
backend by design: layers and project are PyQGIS-backed (TASK-25.2), while
settings, styles and notifications are still the in-memory doubles until
TASK-25.3 and TASK-25.4 land. Each of those tasks replaces its double here.

The fake imports are lazy inside the factory on purpose: while a slice is being
added, one missing service fails its own test instead of breaking collection for
the whole directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import BufferRequest, CentroidRequest
from qgis_sdk.services import (
    Algorithms,
    Layers,
    Notifications,
    Project,
    Settings,
    Styles,
)

NATIVE_ENV_FLAG = "QGIS_SDK_NATIVE_SERVICES"
# Catalog identifiers, identical on both backends because the catalog is shipped
# with the package rather than declared by the test.
COMPATIBLE_STYLE = "reference/point-output"
INCOMPATIBLE_STYLE = "reference/line-output"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "reference"
FIXTURE_DATASET = FIXTURE_ROOT / "points.geojson"
LINE_DATASET = FIXTURE_ROOT / "lines.geojson"
MINIMAL_DATASET = FIXTURE_ROOT / "points-minimal.geojson"
FIXTURE_NAME = "points"
FIXTURE_GEOMETRY = "point"
FIXTURE_FIELDS = ("id", "value")
# RFC 7946 GeoJSON is WGS 84, and GDAL reports it as such; the fake declares the
# same value the provider will read from the file.
FIXTURE_CRS = "EPSG:4326"
# The reference workflow's distance operation needs a projected, metre-based
# working CRS; WGS 84 is exactly what decision-19 forbids here.
WORKING_CRS = "EPSG:3857"
# A projected CRS whose map units are US survey feet: metres would be wrong.
FEET_CRS = "EPSG:2227"


@dataclass(frozen=True, slots=True)
class Services:
    """Everything one contract test needs, supplied by the backend under test."""

    algorithms: Algorithms
    layers: Layers
    project: Project
    settings: Settings
    styles: Styles
    notifications: Notifications
    scope: ResourceScope
    dataset: Path
    line_dataset: Path
    minimal_dataset: Path
    compatible_style: str
    incompatible_style: str
    select: Callable[[str, Sequence[int]], None]
    working_crs: str = WORKING_CRS
    work_directory: Path | None = None


def _qgis_python_path() -> Path:
    """Return the directory holding the QGIS Python bindings of this prefix."""
    return Path(sys.prefix) / "share" / "qgis" / "python"


def _native_available() -> bool:
    """Whether the opt-in native backend can be registered for this run."""
    return os.environ.get(NATIVE_ENV_FLAG) == "1" and _qgis_python_path().is_dir()


# Identifies one test session's settings prefix, so values written by the native
# backend cannot outlive the run or collide with another session's.
_SESSION_TOKEN = f"{os.getpid()}-{int(__import__('time').time())}"

_APPLICATION: object | None = None
# Temporary outputs of the native backend. One root per session, removed with
# the application; each services instance gets its own directory so a test can
# never observe another test's files.
_WORK_ROOT = Path(tempfile.mkdtemp(prefix="qgis-sdk-algorithms-"))
_WORK_DIRECTORIES = 0


def _algorithm_work_directory() -> Path:
    """Return a fresh directory for one native algorithms backend."""
    global _WORK_DIRECTORIES
    _WORK_DIRECTORIES += 1
    directory = _WORK_ROOT / f"services-{_WORK_DIRECTORIES}"
    directory.mkdir(parents=True)
    return directory


def _start_qgis() -> None:
    """Start one headless ``QgsApplication`` for the whole native run."""
    global _APPLICATION
    if _APPLICATION is not None:
        return
    prefix = Path(sys.prefix)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PROJ_LIB", str(prefix / "share" / "proj"))
    os.environ.setdefault("QGIS_PREFIX_PATH", str(prefix))
    bindings = str(_qgis_python_path())
    if bindings not in sys.path:
        sys.path.insert(0, bindings)

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath(str(prefix), True)
    application = QgsApplication([b"qgis-sdk-services-contract"], True)
    application.initQgis()
    _APPLICATION = application


def _fake_services() -> Services:
    from qgis_sdk.testing import (
        FakeAlgorithms,
        FakeLayers,
        FakeProject,
        FakeSettings,
        FakeStyles,
        RecordingNotifications,
    )

    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        FIXTURE_DATASET,
        name=FIXTURE_NAME,
        geometry_type=FIXTURE_GEOMETRY,
        field_names=FIXTURE_FIELDS,
        crs=FIXTURE_CRS,
    )
    layers.register(
        LINE_DATASET,
        name="lines",
        geometry_type="line",
        field_names=("id",),
        crs=FIXTURE_CRS,
    )
    layers.register(
        MINIMAL_DATASET,
        name="points-minimal",
        geometry_type="point",
        field_names=("id",),
        crs=FIXTURE_CRS,
    )
    algorithms = FakeAlgorithms(layers, scope)
    algorithms.declare_output(
        BufferRequest,
        FIXTURE_ROOT / "buffer-output.gpkg",
        name="buffer",
        geometry_type="polygon",
        field_names=FIXTURE_FIELDS,
        crs=WORKING_CRS,
    )
    algorithms.declare_output(
        CentroidRequest,
        FIXTURE_ROOT / "centroid-output.gpkg",
        name="centroid",
        geometry_type="point",
        field_names=FIXTURE_FIELDS,
        crs=FIXTURE_CRS,
    )
    styles = FakeStyles(layers, scope)
    return Services(
        algorithms=algorithms,
        layers=layers,
        project=FakeProject(layers, scope),
        settings=FakeSettings(scope),
        styles=styles,
        notifications=RecordingNotifications(scope),
        scope=scope,
        dataset=FIXTURE_DATASET,
        line_dataset=LINE_DATASET,
        minimal_dataset=MINIMAL_DATASET,
        compatible_style=COMPATIBLE_STYLE,
        incompatible_style=INCOMPATIBLE_STYLE,
        select=layers.select,
    )


def _native_services() -> Services:
    # Environment and bindings path must be in place before QGIS is imported.
    _start_qgis()

    from qgis.core import QgsProject
    from qgis_sdk.adapters.qgis import (
        NativeAlgorithms,
        NativeLayers,
        NativeNotifications,
        NativeProject,
        NativeSettings,
    )
    from qgis_sdk.adapters.qgis.styles import NativeStyles

    # Contract tests share one application, so each backend instance starts from
    # an empty project instead of inheriting the previous test's layers.
    QgsProject.instance().removeAllMapLayers()

    work_directory = _algorithm_work_directory()
    scope = ResourceScope()
    layers = NativeLayers(scope)
    project = NativeProject(layers, scope)
    styles = NativeStyles(layers, scope)

    def select(layer_id: str, feature_ids: Sequence[int]) -> None:
        # Selecting is a host action: the curated contract reads a selection and
        # never sets one (decision-19), so this setup drives PyQGIS directly, as
        # a user clicking in QGIS would.
        project.add_layer(layer_id)
        QgsProject.instance().mapLayer(layer_id).selectByIds(list(feature_ids))

    return Services(
        algorithms=NativeAlgorithms(layers, scope, working_directory=work_directory),
        layers=layers,
        project=project,
        # A per-session prefix keeps the run out of the real profile's keys and
        # keeps one test's values out of the next one's.
        settings=NativeSettings(scope, prefix=f"qgis-sdk-contract/{_SESSION_TOKEN}"),
        styles=styles,
        notifications=NativeNotifications(scope),
        scope=scope,
        dataset=FIXTURE_DATASET,
        line_dataset=LINE_DATASET,
        minimal_dataset=MINIMAL_DATASET,
        compatible_style=COMPATIBLE_STYLE,
        incompatible_style=INCOMPATIBLE_STYLE,
        select=select,
        work_directory=work_directory,
    )


BACKENDS: dict[str, Callable[[], Services]] = {"fake": _fake_services}
if _native_available():
    BACKENDS["native"] = _native_services


@pytest.fixture(params=sorted(BACKENDS))
def services(request: pytest.FixtureRequest) -> Services:
    """Run the calling contract test against every registered backend."""
    return BACKENDS[request.param]()


@pytest.fixture(scope="session", autouse=True)
def _stop_qgis_after_the_session() -> object:
    """Stop the headless application this suite may have started."""
    yield
    global _APPLICATION
    application = _APPLICATION
    if application is not None:
        _APPLICATION = None
        application.exitQgis()  # type: ignore[attr-defined]
    shutil.rmtree(_WORK_ROOT, ignore_errors=True)


@pytest.fixture
def native_services() -> Services:
    """Build the native backend, skipping when QGIS is not opted in."""
    if "native" not in BACKENDS:
        pytest.skip(f"set {NATIVE_ENV_FLAG}=1 with QGIS installed for native checks")
    return BACKENDS["native"]()
