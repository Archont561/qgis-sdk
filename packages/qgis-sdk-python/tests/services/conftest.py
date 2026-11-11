"""One contract suite, one entry per service backend.

TASK-25.1 requires the native adapter to be held to these same tests rather than
to a parallel suite, so a backend joins by adding a factory to ``BACKENDS`` and
every contract test then runs against it unchanged. Fake/native parity is
therefore a property of the test run, not a claim in a review.

The ``native`` backend is registered only when ``QGIS_SDK_NATIVE_SERVICES=1`` and
the QGIS Python bindings of the active prefix exist, so the ordinary QGIS-free
run stays pure and the opt-in run exercises real QGIS; its parameter carries the
``qgis`` layer marker, so ``-m qgis`` and ``-m pure`` split it like any other
test. The application itself is the session's one (``tests/layers.py``). It is a *partial* native
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
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import connection_fixtures as connection_files
import layer_kind_fixtures as fixture_files
import layers as test_layers
import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.files import FilesService
from qgis_sdk.models import BufferRequest, CentroidRequest, FileRef
from qgis_sdk.models.canvas import CanvasExtent, CanvasPoint
from qgis_sdk.services import (
    Algorithms,
    Canvas,
    Connections,
    Features,
    Layers,
    Layouts,
    Notifications,
    Project,
    Rasters,
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
# The box around the three reference points. The fake is told it; the native
# canvas computes it from the geometry, and the contract asserts one covers the
# other rather than pretending the two are byte-identical.
FIXTURE_EXTENT = CanvasExtent(
    x_min=21.0, y_min=52.0, x_max=21.2, y_max=52.2, crs=FIXTURE_CRS
)
# The map theme both backends declare: a theme is project configuration, not a
# canvas operation, so each backend is asked to provide one by name.
DECLARED_THEME = "reference"

# -- the raster fixture (TASK-87) -------------------------------------------
# A three-by-two ASCII grid, because the file has to be readable in review; the
# native backend converts it to a GeoTIFF at setup, which is the format the
# contract is about. Both backends declare the same numbers.
RASTER_DATASET = FIXTURE_ROOT / "elevation.asc"
RASTER_NAME = "elevation"
RASTER_EXTENT = CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2)
RASTER_RESOLUTION = (0.1, 0.1)
RASTER_BAND_COUNT = 1
RASTER_DATA_TYPE = "Float64"
RASTER_NO_DATA = -9999.0
# 1, 2, 3 in the top row; 4, no-data, 6 in the bottom one.
RASTER_MINIMUM = 1.0
RASTER_MAXIMUM = 6.0
RASTER_MEAN = 3.2
#: GDAL's statistics pass reports the *sample* standard deviation, dividing the
#: squared deviations by ``n - 1``: five valid cells give a divisor of four.
RASTER_STD_DEV = 1.9235384061671346
RASTER_VALID_CELLS = 5
RASTER_NO_DATA_CELLS = 1
#: Column 0 of the top row, and the hole in the bottom row beside it.
RASTER_VALUE_POINT = CanvasPoint(x=21.05, y=52.15)
RASTER_HOLE_POINT = CanvasPoint(x=21.15, y=52.05)
RASTER_VALUE = 1.0
# -- the layer-kind fixtures (TASK-91) ----------------------------------------
#: The mesh both backends describe: an SMS/ADCIRC ``.2dm`` three-vertex,
#: one-triangle surface with no result file beside it. The file is text, so it is
#: checked in and reviewable; MDAL reads it natively and reports one dataset
#: group holding no datasets, which is what the fake is told too - a mesh with
#: geometry and no result on it is a mesh, not a broken one.
MESH_DATASET = FIXTURE_ROOT / "lagoon.2dm"
MESH_NAME = "lagoon"
MESH_VERTICES = 3
MESH_FACES = 1
MESH_GROUPS = 1
#: The annotation layer both backends create. It has no dataset: the contract is
#: that a new one starts empty and is listed like any other layer.
ANNOTATION_NAME = "notes"
#: The box the three mesh vertices cover, which a tiled scene answers instead of
#: a tile count.
MESH_EXTENT = (21.0, 52.0, 21.2, 52.2)
#: The three containers the native half opens are built by
#: :mod:`layer_kind_fixtures` rather than committed: a LAS header, an MBTiles
#: database and a ``tileset.json`` are either binary or a directory of one file,
#: so the fake keys the same paths and one contract test names one file.
POINT_CLOUD_DATASET = FIXTURE_ROOT / "survey.las"
POINT_CLOUD_NAME = fixture_files.POINT_CLOUD_NAME
POINT_CLOUD_COUNT = len(fixture_files.POINT_CLOUD_POINTS)
VECTOR_TILE_DATASET = FIXTURE_ROOT / "basemap.mbtiles"
VECTOR_TILE_NAME = fixture_files.VECTOR_TILE_NAME
TILED_SCENE_DATASET = FIXTURE_ROOT / "scene" / "tileset.json"
#: A 3D Tiles set is called ``tileset.json`` by convention, and every adapter in
#: this repository names a layer after its file's stem - so the name a page sees
#: is ``tileset``, not the folder the file sits in.
TILED_SCENE_NAME = TILED_SCENE_DATASET.stem

#: The nested group structure the project-tree contract builds on both backends.
ROOT_GROUP = "Elevation"
CHILD_GROUP = "Detail"

# -- the print-layout fixture (TASK-89) --------------------------------------
#: The layout both backends describe: two pages, no atlas. Two on purpose - it
#: is the smallest layout an image export has to refuse and a PDF has to hold.
LAYOUT_NAME = "report"
LAYOUT_PAGES = 2
#: A one-page layout, for the formats that hold exactly one image.
SINGLE_PAGE_LAYOUT = "cover"
#: The layout whose atlas covers the three reference points, in feature order.
ATLAS_NAME = "atlas"
ATLAS_FEATURE_IDS = (1, 2, 3)
ATLAS_PATTERN = "sheet-{index:02d}-{feature_id}"
#: The layout a ``.qpt`` template carries: loading the template adds this name,
#: so the file is named after it and the native backend saves a layout of that
#: name as the template.
TEMPLATE_LAYOUT = "templated"

# -- the model file and batch fixture (TASK-94) ------------------------------
#: The model both backends run through ``run_model``: the centroid of every
#: input feature beside a statistics report, the smallest model whose outputs
#: span a layer and a file. The file is QGIS's own ``.model3`` XML in internal
#: version 2 (the format the designer has saved since 3.26), checked in so a
#: reviewer can read what the model declares - a model file is text, like the
#: mesh, and a fixture a reviewer cannot read is a fixture that rots.
REPORT_MODEL = FIXTURE_ROOT / "report.model3"
#: The name the ref answers results under on both backends: ``run_model``
#: reports the ref's name, because that is the handle the caller gave it - a
#: fake has no designer's title to answer instead.
REPORT_MODEL_NAME = REPORT_MODEL.name
#: The two outputs the model exposes, keyed by the destination names version 2
#: gives them (the description of each output, made safe): a vector of
#: centroids and the statistics report beside it.
MODEL_CENTROIDS_OUTPUT = "centroids"
MODEL_REPORT_OUTPUT = "report"
#: The model's own input parameter and the field the statistics child reports.
MODEL_INPUT = "FEATS"
MODEL_FIELD = "value"


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
    # The files service the algorithms backend mints its file outputs through.
    files: FilesService | None = None
    #: Layer data, expressions and editing (TASK-86). ``None`` while a backend
    #: has not joined the contract, so one slice failing is one test failing.
    features: Features | None = None
    #: Registered data-source connections and auth configuration ids (TASK-92).
    #: ``None`` while a backend has not joined the contract.
    connections: Connections | None = None
    #: Put one authentication configuration in the registry and answer the id
    #: the registry gave it; cleaned up with the backend's scope. A test never
    #: writes an id it expects back, because the registry chooses it on both
    #: backends.
    declare_auth_configuration: Callable[[str], str] | None = None
    #: The PostGIS fixture connection's name when the backend holds one;
    #: ``None`` records "blocked by environment" - no server answers, so the
    #: row is recorded rather than pretended (TASK-92's acceptance criterion).
    postgis_connection: str | None = None
    #: A layer that may be edited, freshly prepared for one test. Native copies
    #: the fixture so a commit writes to a file the test owns; the fake declares
    #: its own layer, so nothing on disk is touched.
    editable_layer: Callable[[], str] | None = None
    #: Print layouts and atlases (TASK-89). ``None`` while a backend has not
    #: joined the layouts contract, so one slice failing is one test failing.
    layouts: Layouts | None = None
    #: Builds the layouts the contract describes: two pages, a one-page layout,
    #: an atlas over the three reference points, and a ``.qpt`` template.
    #: Declaring is *setup*, like ``declare_groups``: the native backend has to
    #: put them in the project and open the coverage layer, and the fake has to
    #: be told the same names, so the layouts tests ask for exactly that.
    declare_layouts: Callable[[], None] | None = None
    #: Drives the layouts service's own job service one round trip - submit,
    #: run the worker body, deliver - because the service owns that job service
    #: (a plugin that declares no jobs still exports as a job).
    drive_layouts: Callable[[], None] | None = None
    #: The work items the layouts jobs asked the worker backend to show, oldest
    #: first: a test reads their ``progress`` to see the fractions a render
    #: reported one at a time, which delivery coalesces per tick.
    layout_work_items: Callable[[], tuple] | None = None
    #: The directory a destination-less export is written into.
    layout_directory: Callable[[], Path] | None = None
    #: The ``.qpt`` template ``load_template`` loads, named after the layout it
    #: carries so both backends add the same name to the project.
    layout_template: Callable[[], Path] | None = None
    #: The ``.model3`` model file ``run_model`` runs (TASK-94). ``None`` while a
    #: backend has not joined the model contract, so one slice failing is one
    #: test failing.
    model_file: Callable[[], FileRef] | None = None
    #: Drives the algorithms service's own job service one round trip - submit,
    #: run the worker body, deliver - because a batch is a job even for a
    #: plugin that declares no jobs of its own.
    drive_algorithms: Callable[[], None] | None = None
    #: The work items the batch asked the worker backend to show, oldest first:
    #: a test reads their ``progress`` to see the fractions a batch reported one
    #: per request, which delivery coalesces per tick.
    algorithm_work_items: Callable[[], tuple] | None = None
    #: The id of the layer holding the reference points (ids 1-3, values a-c).
    #: The fakes key layers by name; a native layer's id is the one QGIS gave it
    #: when it opened the file, so a contract test names the layer the backend
    #: reports instead of assuming the fake's key is an id. It opens on first
    #: use, because a backend that has opened nothing must stay empty for the
    #: tests that assert exactly that.
    fixture_layer: Callable[[], str] | None = None
    #: The file behind :attr:`editable_layer` when a backend writes one to disk.
    #: ``None`` for a backend whose editable layer exists only in memory.
    editable_dataset: Path | None = None
    #: The map the user is looking at (TASK-85). ``None`` while a backend has not
    #: joined the canvas contract, so one slice failing is one test failing.
    canvas: Canvas | None = None
    #: Draws ``shape`` on the canvas the way a user would, so an open capture
    #: session answers. Selecting is a host action in the features contract for
    #: the same reason: the curated surface reads a drawing, it does not make one.
    draw: Callable[[str], None] | None = None
    #: Whether a capture session is open - the canvas-equivalent of asking the
    #: map tool, so ``capture`` and its canceller can be asserted on both backends.
    is_drawing: Callable[[], bool] | None = None
    #: Declares a map theme over whatever layers the project holds, because
    #: ``apply_theme`` picks a theme and never creates one.
    declare_theme: Callable[[str], None] | None = None
    #: Raster reads (TASK-87). ``None`` while a backend has not joined the
    #: raster contract, so one slice failing is one test failing.
    rasters: Rasters | None = None
    #: Opens the fixture raster and answers its layer id. Native converts the
    #: checked-in grid to a GeoTIFF first; the fake declares the same numbers.
    open_raster: Callable[[], str] | None = None
    #: The raster file the backend actually reads: the checked-in grid for the
    #: fake, the GeoTIFF the native backend built from it.
    raster_dataset: Path | None = None
    #: Opens the mesh fixture and answers its layer id (TASK-91). ``None`` while a
    #: backend has not joined the layer-kind contract, so one slice failing is one
    #: test failing.
    open_mesh: Callable[[], str] | None = None
    #: The mesh file the backend actually reads.
    mesh_dataset: Path | None = None
    #: Creates an annotation layer under the name it is given and answers its id.
    #: An annotation layer is created rather than opened, so the contract names
    #: it; both backends start one empty.
    open_annotation: Callable[[str], str] | None = None
    #: Opens the point cloud, vector tile and tiled-scene fixtures (TASK-91) and
    #: answers each layer's id. The three files are built rather than checked in
    #: (``layer_kind_fixtures``); ``None`` while a backend has not joined the kind
    #: contract, so one slice failing is one test failing.
    open_point_cloud: Callable[[], str] | None = None
    point_cloud_dataset: Path | None = None
    open_vector_tile: Callable[[], str] | None = None
    vector_tile_dataset: Path | None = None
    open_tiled_scene: Callable[[], str] | None = None
    tiled_scene_dataset: Path | None = None
    #: A fresh directory one test may write project files into.
    project_directory: Callable[[], Path] | None = None
    #: Creates the nested group structure (``ROOT_GROUP`` -> ``CHILD_GROUP``)
    #: in the project and answers the two group ids, deepest last. Building a
    #: tree is project *setup* - QGIS's own group dialog does it - and the
    #: service edits a tree it was given. The ids are the backend's own: the
    #: fake mints them, QGIS gives a group no id at all and the adapter derives
    #: one, so a contract test names what the backend reported.
    declare_groups: Callable[[], tuple[str, str]] | None = None


def _native_available() -> bool:
    """Whether the opt-in native backend can be registered for this run."""
    return (
        os.environ.get(NATIVE_ENV_FLAG) == "1"
        and test_layers.qgis_bindings() is not None
    )


# Identifies one test session's settings prefix, so values written by the native
# backend cannot outlive the run or collide with another session's.
_SESSION_TOKEN = f"{os.getpid()}-{int(__import__('time').time())}"

# Temporary outputs of the native backend. One root per session, removed with
# the application; each services instance gets its own directory so a test can
# never observe another test's files.
_WORK_ROOT = Path(tempfile.mkdtemp(prefix="qgis-sdk-algorithms-"))
_WORK_DIRECTORIES = 0
_FEATURE_DIRECTORIES = 0
_PROJECT_DIRECTORIES = 0
_LAYOUT_DIRECTORIES = 0
_LAYER_KIND_DIRECTORIES = 0


def _algorithm_work_directory() -> Path:
    """Return a fresh directory for one native algorithms backend."""
    global _WORK_DIRECTORIES
    _WORK_DIRECTORIES += 1
    directory = _WORK_ROOT / f"services-{_WORK_DIRECTORIES}"
    directory.mkdir(parents=True)
    return directory


def _layer_kind_work_directory() -> Path:
    """Return a fresh directory for one native layer-kind backend's fixtures.

    The three containers are written here rather than checked in: a LAS file and
    an MBTiles database are binary, and a tileset is a directory. Each backend
    gets its own, so one test can never read a file another test wrote.
    """
    global _LAYER_KIND_DIRECTORIES
    _LAYER_KIND_DIRECTORIES += 1
    directory = _WORK_ROOT / f"layer-kinds-{_LAYER_KIND_DIRECTORIES}"
    directory.mkdir(parents=True)
    return directory


def _feature_work_directory() -> Path:
    """Return a fresh directory for one native features backend.

    The editable copy cannot share the algorithms directory, even in a
    subdirectory: those tests walk their directory and assert that the run's
    output is the only file in it, so a fixture row file would be a second file
    they did not write.
    """
    global _FEATURE_DIRECTORIES
    _FEATURE_DIRECTORIES += 1
    directory = _WORK_ROOT / f"features-{_FEATURE_DIRECTORIES}"
    directory.mkdir(parents=True)
    return directory


def _project_work_directory() -> Path:
    """Return a fresh directory for one backend's project files."""
    global _PROJECT_DIRECTORIES
    _PROJECT_DIRECTORIES += 1
    directory = _WORK_ROOT / f"project-{_PROJECT_DIRECTORIES}"
    directory.mkdir(parents=True)
    return directory


def _layout_work_directory() -> Path:
    """Return a fresh directory for one backend's layout exports and template.

    One per backend, not one per test: a destination-less export numbers its own
    files in here (``report.pdf``, ``report-2.pdf``), so a test that exports
    twice sees the numbering the service documents rather than a fresh name.
    """
    global _LAYOUT_DIRECTORIES
    _LAYOUT_DIRECTORIES += 1
    directory = _WORK_ROOT / f"layouts-{_LAYOUT_DIRECTORIES}"
    directory.mkdir(parents=True)
    return directory


#: The GeoTIFF the native backend reads, built once per session from the
#: checked-in grid: the fixture itself stays reviewable text, and the format the
#: contract is about is produced by the same GDAL a plugin ships with.
_GEOTIFF: list[Path] = []


def _geotiff_fixture() -> Path:
    """Convert ``elevation.asc`` to a GeoTIFF, once per session."""
    if _GEOTIFF:
        return _GEOTIFF[0]
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransformContext,
        QgsRasterFileWriter,
        QgsRasterLayer,
        QgsRasterPipe,
    )

    source = QgsRasterLayer(str(RASTER_DATASET), RASTER_NAME, "gdal")
    if not source.isValid():
        pytest.fail(f"the raster fixture {RASTER_DATASET} is not readable")
    # The grid's own ``.prj`` is a sidecar the driver may or may not load, and
    # the contract is about a raster that knows its CRS: the conversion declares
    # it outright so the GeoTIFF carries EPSG:4326 either way.
    crs = source.crs()
    if not crs.isValid():
        crs = QgsCoordinateReferenceSystem(FIXTURE_CRS)
    destination = _WORK_ROOT / "elevation.tif"
    pipe = QgsRasterPipe()
    if not pipe.set(source.dataProvider().clone()):
        pytest.fail("the raster fixture's provider refused the writer's pipe")
    writer = QgsRasterFileWriter(str(destination))
    writer.setOutputFormat("GTiff")
    written = writer.writeRaster(
        pipe,
        source.width(),
        source.height(),
        source.extent(),
        crs,
        QgsCoordinateTransformContext(),
    )
    if written != QgsRasterFileWriter.NoError:
        pytest.fail(f"the raster fixture could not be written: {written}")
    _GEOTIFF.append(destination)
    return destination


#: What the fake answers a drawing with: the shape each capture session asks
#: for, as the WKT the fake never converts. The vertices are the same ones the
#: native driver clicks, so both backends describe the same drawing.
_DRAWN_WKT = {
    "point": ("POINT (21.1 52.1)", 1, 1),
    "line": ("LINESTRING (21 52, 21.2 52.2)", 1, 2),
    "polygon": ("POLYGON ((21 52, 21.2 52, 21.2 52.2, 21 52))", 1, 4),
}


def _drawn_geometry(shape: str):
    """The geometry the fake hands back for a finished drawing of ``shape``."""
    from qgis_sdk.models import Geometry

    value, parts, vertices = _DRAWN_WKT[shape]
    return Geometry(
        encoding="wkt",
        value=value,
        geometry_type=shape,
        crs=FIXTURE_CRS,
        part_count=parts,
        vertex_count=vertices,
    )


def _point_wkt(x: float, y: float):
    """A WKT point the fake declares; the fake never converts encodings."""
    from qgis_sdk.models import Geometry

    return Geometry(
        encoding="wkt", value=f"POINT ({x} {y})", geometry_type="point", crs=FIXTURE_CRS
    )


def _fake_services() -> Services:
    from qgis_sdk.models import RasterStatistics
    from qgis_sdk.testing import (
        ConnectionDeclaration,
        DeclaredOutput,
        FakeAlgorithms,
        FakeAlgorithmSetup,
        FakeCanvas,
        FakeConnections,
        FakeFiles,
        FakeLayers,
        FakeLayouts,
        FakeProject,
        FakeRasters,
        FakeSettings,
        FakeStyles,
        FakeWorkers,
        OtherLayerDeclaration,
        RecordingNotifications,
        TableDeclaration,
        VectorLayerDeclaration,
    )

    scope = ResourceScope()
    # The raster fake first, because the vector fake holds it: a raster is a
    # layer too, so ``list_layers`` answers both kinds (TASK-87).
    rasters = FakeRasters(scope)
    layers = FakeLayers(scope, rasters=rasters)
    layers.register(
        VectorLayerDeclaration(
            FIXTURE_DATASET,
            name=FIXTURE_NAME,
            geometry_type=FIXTURE_GEOMETRY,
            field_names=FIXTURE_FIELDS,
            crs=FIXTURE_CRS,
        )
    )
    layers.register(
        VectorLayerDeclaration(
            LINE_DATASET,
            name="lines",
            geometry_type="line",
            field_names=("id",),
            crs=FIXTURE_CRS,
        )
    )
    layers.register(
        VectorLayerDeclaration(
            MINIMAL_DATASET,
            name="points-minimal",
            geometry_type="point",
            field_names=("id",),
            crs=FIXTURE_CRS,
        )
    )
    files = FakeFiles(scope, owner="plugin:contract")
    algo_workers = FakeWorkers()
    layout_workers = FakeWorkers()
    layout_directory = _layout_work_directory()
    layouts = FakeLayouts(
        scope,
        workers=layout_workers,
        files=files,
        working_directory=layout_directory,
    )

    def declare_layouts() -> None:
        """Declare the layouts the contract describes, and write a template."""
        layouts.declare_layout(LAYOUT_NAME, pages=LAYOUT_PAGES)
        layouts.declare_layout(SINGLE_PAGE_LAYOUT)
        layouts.declare_atlas(
            ATLAS_NAME,
            coverage_layer=FIXTURE_NAME,
            feature_ids=ATLAS_FEATURE_IDS,
        )
        template().write_text("<!-- the fake only has to find the template -->")

    def template() -> Path:
        return layout_directory / f"{TEMPLATE_LAYOUT}.qpt"

    def drive_layouts() -> None:
        """One round trip through the layouts service's own job service."""
        service = layouts.jobs
        service.tick()
        layout_workers.run_all()
        service.tick()

    algorithms = FakeAlgorithms(
        FakeAlgorithmSetup(layers, scope, files=files, workers=algo_workers)
    )
    algorithms.declare_output(
        DeclaredOutput(
            BufferRequest,
            FIXTURE_ROOT / "buffer-output.gpkg",
            name="buffer",
            geometry_type="polygon",
            field_names=FIXTURE_FIELDS,
            crs=WORKING_CRS,
        )
    )
    algorithms.declare_output(
        DeclaredOutput(
            CentroidRequest,
            FIXTURE_ROOT / "centroid-output.gpkg",
            name="centroid",
            geometry_type="point",
            field_names=FIXTURE_FIELDS,
            crs=FIXTURE_CRS,
        )
    )
    # The generic run answers from scripts: the same declared datasets for
    # the vector algorithms, a real file on disk for the report, and the
    # scalars the native run of ``native:basicstatisticsforfields`` yields
    # over the three-feature fixture.
    algorithms.script_run(
        "native:buffer", {"OUTPUT": FIXTURE_ROOT / "buffer-output.gpkg"}
    )
    algorithms.script_run(
        "native:centroids", {"OUTPUT": FIXTURE_ROOT / "centroid-output.gpkg"}
    )
    algorithms.script_run(
        "native:basicstatisticsforfields",
        {"COUNT": 3, "OUTPUT_HTML_FILE": MINIMAL_DATASET},
    )
    # The model file (TASK-94), granted once so the scripted answers key the
    # same ref the tests run. The fake never parses the XML - a model run's
    # shape is the contract here, and the native lane reads the real file -
    # but the answers are the kinds the file declares: an owned layer beside
    # a readable report.
    from qgis_sdk.models import VectorLayerInfo

    model_ref = files.grant_file(REPORT_MODEL)
    algorithms.script_run_model(
        model_ref,
        {
            MODEL_CENTROIDS_OUTPUT: VectorLayerInfo(
                id="model:centroids",
                name=MODEL_CENTROIDS_OUTPUT,
                geometry_type="point",
                field_names=FIXTURE_FIELDS,
                crs=FIXTURE_CRS,
            ),
            MODEL_REPORT_OUTPUT: files.grant_file(MINIMAL_DATASET),
        },
    )

    def drive_algorithms() -> None:
        """One round trip through the algorithms service's own job service."""
        service = algorithms.jobs
        service.tick()
        algo_workers.run_all()
        service.tick()

    from qgis_sdk.testing import FakeFeatures

    features = FakeFeatures(scope)
    features.declare(
        FIXTURE_NAME,
        fields=FIXTURE_FIELDS,
        rows=[
            (1, {"id": 1, "value": "a"}, _point_wkt(21.0, 52.0)),
            (2, {"id": 2, "value": "b"}, _point_wkt(21.1, 52.1)),
            (3, {"id": 3, "value": "c"}, _point_wkt(21.2, 52.2)),
        ],
    )
    editable = features.declare(
        "editable",
        fields=FIXTURE_FIELDS,
        rows=[(1, {"id": 1, "value": "a"}, _point_wkt(21.0, 52.0))],
    )
    del editable
    styles = FakeStyles(layers, scope)
    # The connections registry (TASK-92): the GeoPackage fixture every backend
    # declares, the PostGIS one the fake always holds, and the connection
    # nothing serves. The GeoPackage answers provider ``ogr`` because that is
    # the registry key its native half is listed under - QGIS implements the
    # GeoPackage connection methods in OGR.
    connections = FakeConnections(layers)
    connections.declare_connection(
        ConnectionDeclaration(
            connection_files.GPKG_CONNECTION, schemas=(), accepts_auth=False
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.GPKG_CONNECTION,
            connection_files.GPKG_ROADS,
            kind=connection_files.GPKG_ROADS_KIND,
            geometries=connection_files.GPKG_ROADS_GEOMETRIES,
            fields=connection_files.GPKG_ROADS_FIELDS,
            crs=connection_files.FIXTURE_CRS,
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.GPKG_CONNECTION,
            connection_files.GPKG_PLACES,
            kind=connection_files.GPKG_PLACES_KIND,
            geometries=connection_files.GPKG_PLACES_GEOMETRIES,
            fields=connection_files.GPKG_PLACES_FIELDS,
            crs=connection_files.FIXTURE_CRS,
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.GPKG_CONNECTION,
            connection_files.GPKG_NOTES,
            kind=connection_files.GPKG_NOTES_KIND,
            geometries=connection_files.GPKG_NOTES_GEOMETRIES,
            fields=connection_files.GPKG_NOTES_FIELDS,
        )
    )
    connections.declare_connection(
        ConnectionDeclaration(
            connection_files.POSTGIS_CONNECTION,
            provider="postgres",
            schemas=(connection_files.POSTGIS_SCHEMA,),
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.POSTGIS_CONNECTION,
            connection_files.POSTGIS_POINTS,
            provider="postgres",
            schema=connection_files.POSTGIS_SCHEMA,
            kind=connection_files.POSTGIS_POINTS_KIND,
            geometries=connection_files.POSTGIS_POINTS_GEOMETRIES,
            fields=connection_files.POSTGIS_POINTS_FIELDS,
            crs=connection_files.FIXTURE_CRS,
        )
    )
    connections.declare_connection(
        ConnectionDeclaration(
            connection_files.BROKEN_CONNECTION,
            provider="postgres",
            valid=False,
            message="connection to server at 127.0.0.1, port 1 failed: Connection refused",
        )
    )
    rasters.register(
        RASTER_DATASET,
        name=RASTER_NAME,
        extent=RASTER_EXTENT,
        band_count=RASTER_BAND_COUNT,
        data_types=(RASTER_DATA_TYPE,),
        no_data=(RASTER_NO_DATA,),
        resolution=RASTER_RESOLUTION,
        crs=FIXTURE_CRS,
        values=(RASTER_VALUE,),
        holes=((RASTER_HOLE_POINT.x, RASTER_HOLE_POINT.y),),
        statistics={
            1: RasterStatistics(
                band=1,
                minimum=RASTER_MINIMUM,
                maximum=RASTER_MAXIMUM,
                mean=RASTER_MEAN,
                std_dev=RASTER_STD_DEV,
                valid_count=RASTER_VALID_CELLS,
                no_data_count=RASTER_NO_DATA_CELLS,
            )
        },
    )
    # The mesh the layer-kind contract opens, declared with the numbers the
    # ``.2dm`` fixture holds so both backends report the same three. No CRS is
    # declared because the file has none: MDAL reads no projection out of a
    # ``.2dm``, so the native layer answers null and the fake must agree.
    layers.register_layer(
        OtherLayerDeclaration(
            MESH_DATASET,
            name=MESH_NAME,
            kind="mesh",
            detail={
                "vertex_count": MESH_VERTICES,
                "face_count": MESH_FACES,
                "group_count": MESH_GROUPS,
            },
        )
    )
    # The three containers the native half builds are declared with the numbers
    # the built files hold. A point cloud's attributes are PDAL's dimension
    # names, of which the contract asks for ``Z`` on both backends; a vector
    # tile's zoom range is what its MBTiles metadata says; a tiled scene answers
    # the box its tileset's region covers.
    layers.register_layer(
        OtherLayerDeclaration(
            POINT_CLOUD_DATASET,
            name=POINT_CLOUD_NAME,
            kind="point_cloud",
            detail={
                "point_count": POINT_CLOUD_COUNT,
                "attribute_names": ("X", "Y", "Z"),
            },
        )
    )
    layers.register_layer(
        OtherLayerDeclaration(
            VECTOR_TILE_DATASET,
            name=VECTOR_TILE_NAME,
            kind="vector_tile",
            detail={
                "source_type": "mbtiles",
                "min_zoom": fixture_files.VECTOR_TILE_MIN_ZOOM,
                "max_zoom": fixture_files.VECTOR_TILE_MAX_ZOOM,
            },
        )
    )
    layers.register_layer(
        OtherLayerDeclaration(
            TILED_SCENE_DATASET,
            name=TILED_SCENE_NAME,
            kind="tiled_scene",
            detail={
                "extent": {
                    "x_min": fixture_files.TILED_SCENE_REGION[0],
                    "y_min": fixture_files.TILED_SCENE_REGION[1],
                    "x_max": fixture_files.TILED_SCENE_REGION[2],
                    "y_max": fixture_files.TILED_SCENE_REGION[3],
                }
            },
        )
    )
    project = FakeProject(layers, scope)
    project_directory = _project_work_directory()

    def declare_groups() -> tuple[str, str]:
        from qgis_sdk.models import LayerNode

        project.set_tree(
            (
                LayerNode(id="group-root", name=ROOT_GROUP, kind="group"),
                LayerNode(
                    id="group-child",
                    name=CHILD_GROUP,
                    kind="group",
                    parent="group-root",
                ),
            )
        )
        root_id, child_id = project.layer_tree().group_ids()
        return root_id, child_id

    canvas = FakeCanvas(
        scope,
        layer_extents={FIXTURE_NAME: FIXTURE_EXTENT},
        themes=(DECLARED_THEME,),
    )
    return Services(
        canvas=canvas,
        draw=lambda shape: canvas.draw(_drawn_geometry(shape)),
        is_drawing=lambda: bool(canvas.open_captures()),
        declare_theme=lambda name: canvas.declare_theme(name),
        files=files,
        algorithms=algorithms,
        features=features,
        editable_layer=lambda: "editable",
        fixture_layer=lambda: FIXTURE_NAME,
        layers=layers,
        rasters=rasters,
        layouts=layouts,
        declare_layouts=declare_layouts,
        drive_layouts=drive_layouts,
        layout_work_items=lambda: tuple(layout_workers.items),
        layout_directory=lambda: layout_directory,
        layout_template=template,
        model_file=lambda: model_ref,
        drive_algorithms=drive_algorithms,
        algorithm_work_items=lambda: tuple(algo_workers.items),
        open_raster=lambda: rasters.open_raster(RASTER_DATASET).id,
        raster_dataset=RASTER_DATASET,
        open_mesh=lambda: layers.open_mesh(MESH_DATASET).id,
        mesh_dataset=MESH_DATASET,
        open_annotation=lambda name: layers.open_annotation(name).id,
        open_point_cloud=lambda: layers.open_point_cloud(POINT_CLOUD_DATASET).id,
        point_cloud_dataset=POINT_CLOUD_DATASET,
        open_vector_tile=lambda: layers.open_vector_tile(VECTOR_TILE_DATASET).id,
        vector_tile_dataset=VECTOR_TILE_DATASET,
        open_tiled_scene=lambda: layers.open_tiled_scene(TILED_SCENE_DATASET).id,
        tiled_scene_dataset=TILED_SCENE_DATASET,
        project=project,
        project_directory=lambda: project_directory,
        declare_groups=declare_groups,
        settings=FakeSettings(scope),
        styles=styles,
        connections=connections,
        declare_auth_configuration=connections.declare_auth_configuration,
        postgis_connection=connection_files.POSTGIS_CONNECTION,
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
    # The session's application, started here if no module asked before.
    test_layers.start_application()

    from qgis.core import QgsProject
    from qgis_sdk.adapters.qgis import (
        AlgorithmWiring,
        NativeAlgorithms,
        NativeCanvas,
        NativeLayers,
        NativeNotifications,
        NativeProject,
        NativeRasters,
        NativeSettings,
    )
    from qgis_sdk.adapters.qgis.connections import NativeConnections
    from qgis_sdk.adapters.qgis.styles import NativeStyles

    # Contract tests share one application, so each backend instance starts from
    # an empty project instead of inheriting the previous test's layers - and an
    # empty *file*, so a test that saves before reading is not answering with
    # the file another test read.
    QgsProject.instance().removeAllMapLayers()
    _forget_project_file(QgsProject.instance())

    work_directory = _algorithm_work_directory()
    scope = ResourceScope()
    rasters = NativeRasters(scope)
    layers = NativeLayers(scope, rasters=rasters)
    project = NativeProject(layers, scope, rasters=rasters)
    styles = NativeStyles(layers, scope)
    connections = NativeConnections(layers)
    project_directory = _project_work_directory()
    raster_file = _geotiff_fixture()
    # The point cloud, vector tile and tiled-scene fixtures (TASK-91), built once
    # per backend. A layer kind is opened the way a user opens it: the provider
    # is handed a real file and the description is what it read out of it.
    layer_kind_directory = _layer_kind_work_directory()
    point_cloud_file = fixture_files.write_point_cloud(
        layer_kind_directory / "survey.las"
    )
    vector_tile_file = fixture_files.write_vector_tiles(
        layer_kind_directory / "basemap.mbtiles"
    )
    tiled_scene_file = fixture_files.write_tiled_scene(
        layer_kind_directory / "scene" / "tileset.json"
    )
    # The connections registry (TASK-92): the fixture GeoPackage file is built
    # and its connection registered in QGIS's own settings, and the scope
    # removes it again - a contract run never leaves a trace in the profile.
    from qgis.core import QgsProviderRegistry

    registry = QgsProviderRegistry.instance()
    gpkg_file = connection_files.write_geopackage(
        layer_kind_directory / connection_files.GPKG_FILE
    )
    ogr = registry.providerMetadata("ogr")
    stored = ogr.createConnection(str(gpkg_file), {})
    stored.store(connection_files.GPKG_CONNECTION)
    scope.on_close(lambda: ogr.deleteConnection(connection_files.GPKG_CONNECTION))
    # The connection nothing serves: registered with a password in its settings
    # so the no-secret claim has a secret to refuse, and pointed at a dead port
    # so ``test`` has a verdict to answer - neither needs a server.
    postgres = registry.providerMetadata("postgres")
    broken = postgres.createConnection(connection_files.BROKEN_URI, {})
    broken.store(connection_files.BROKEN_CONNECTION)
    scope.on_close(
        lambda: postgres.deleteConnection(connection_files.BROKEN_CONNECTION)
    )
    # The PostGIS row: registered when QGIS_SDK_TEST_POSTGIS names a server that
    # holds ``public.points``; otherwise the row is blocked by environment.
    postgis_connection = None
    postgis_uri = os.environ.get("QGIS_SDK_TEST_POSTGIS")
    if postgis_uri:
        remote = postgres.createConnection(postgis_uri, {})
        remote.store(connection_files.POSTGIS_CONNECTION)
        scope.on_close(
            lambda: postgres.deleteConnection(connection_files.POSTGIS_CONNECTION)
        )
        postgis_connection = connection_files.POSTGIS_CONNECTION

    def declare_auth_configuration(name: str) -> str:
        from qgis.core import QgsApplication, QgsAuthMethodConfig

        config = QgsAuthMethodConfig()
        config.setName(name)
        manager = QgsApplication.authManager()
        stored = manager.storeAuthenticationConfig(config)
        kept = bool(config.id()) and config.id() in manager.configIds()
        if not stored or not kept:
            pytest.skip(
                "the authentication registry needs a master password this "
                "environment does not set"
            )

        def remove() -> None:
            manager.removeAuthenticationConfig(config.id())

        scope.on_close(remove)
        return config.id()

    opened_rasters: dict[str, str] = {}
    opened_meshes: dict[str, str] = {}
    opened_kinds: dict[str, str] = {}

    def open_raster() -> str:
        if "id" not in opened_rasters:
            opened_rasters["id"] = rasters.open_raster(raster_file).id
        return opened_rasters["id"]

    def open_mesh() -> str:
        if "mesh" not in opened_meshes:
            opened_meshes["mesh"] = layers.open_mesh(MESH_DATASET).id
        return opened_meshes["mesh"]

    def open_annotation(name: str) -> str:
        return layers.open_annotation(name).id

    def _open_once(kind: str, opener: Callable[[], str]) -> str:
        if kind not in opened_kinds:
            opened_kinds[kind] = opener()
        return opened_kinds[kind]

    def open_point_cloud() -> str:
        return _open_once(
            "point_cloud", lambda: layers.open_point_cloud(point_cloud_file).id
        )

    def open_vector_tile() -> str:
        return _open_once(
            "vector_tile", lambda: layers.open_vector_tile(vector_tile_file).id
        )

    def open_tiled_scene() -> str:
        return _open_once(
            "tiled_scene", lambda: layers.open_tiled_scene(tiled_scene_file).id
        )

    def declare_groups() -> tuple[str, str]:
        root = QgsProject.instance().layerTreeRoot()
        root_group = root.insertGroup(0, ROOT_GROUP)
        root_group.addGroup(CHILD_GROUP)
        root_id, child_id = project.layer_tree().group_ids()
        return root_id, child_id

    def select(layer_id: str, feature_ids: Sequence[int]) -> None:
        # Selecting is a host action: the curated contract reads a selection and
        # never sets one (decision-19), so this setup drives PyQGIS directly, as
        # a user clicking in QGIS would.
        project.add_layer(layer_id)
        QgsProject.instance().mapLayer(layer_id).selectByIds(list(feature_ids))

    from qgis_sdk.bridge.authority import HostAuthority

    files = FilesService(HostAuthority(), scope, owner="plugin:contract")
    from qgis_sdk.adapters.qgis import NativeFeatures

    features = NativeFeatures(layers, scope)

    from qgis_sdk.adapters.qgis import NativeLayouts
    from qgis_sdk.testing import FakeWorkers

    algo_workers = FakeWorkers()
    algorithms = NativeAlgorithms(
        AlgorithmWiring(
            layers=layers,
            scope=scope,
            working_directory=work_directory,
            files=files,
            workers=algo_workers,
        )
    )

    def model_file():
        """Grant the checked-in model file, one fresh ref per run."""
        return files.grant_file(REPORT_MODEL)

    def drive_algorithms() -> None:
        """One round trip through the algorithms service's own job service."""
        service = algorithms.jobs
        service.tick()
        algo_workers.run_all()
        service.tick()

    layout_workers = FakeWorkers()
    layout_directory = _layout_work_directory()
    # A fake worker backend on purpose: the contract is about the *render*, and
    # running the body when the test says so keeps an offscreen QgsLayoutExporter
    # off a Qt event loop the pure suite does not have. The real QgsTask path is
    # ``tests/test_jobs_tasks_native.py``'s subject.
    layouts = NativeLayouts(
        scope,
        workers=layout_workers,
        files=files,
        working_directory=layout_directory,
    )

    def template_file() -> Path:
        return layout_directory / f"{TEMPLATE_LAYOUT}.qpt"

    def declare_layouts() -> None:
        """Put the contract's layouts in the project, and save the template."""
        from qgis.core import (
            QgsLayoutItemPage,
            QgsPrintLayout,
            QgsProject,
            QgsReadWriteContext,
            QgsVectorLayer,
        )

        manager = QgsProject.instance().layoutManager()
        # The coverage layer is opened the way a user opens one, and added to the
        # project, because an atlas reads its features from a layer the project
        # holds rather than from a file on its own.
        layer = QgsVectorLayer(str(FIXTURE_DATASET), FIXTURE_NAME, "ogr")
        if not layer.isValid():
            pytest.fail(f"the layout coverage layer {FIXTURE_DATASET} is not readable")
        QgsProject.instance().addMapLayer(layer)
        for name, pages in (
            (LAYOUT_NAME, LAYOUT_PAGES),
            (SINGLE_PAGE_LAYOUT, 1),
            (ATLAS_NAME, 1),
        ):
            if manager.layoutByName(name) is not None:
                continue
            layout = QgsPrintLayout(QgsProject.instance())
            layout.initializeDefaults()
            layout.setName(name)
            for _ in range(pages - 1):
                page = QgsLayoutItemPage(layout)
                page.setPageSize("A4")
                layout.pageCollection().addPage(page)
            manager.addLayout(layout)
        atlas = manager.layoutByName(ATLAS_NAME).atlas()
        atlas.setCoverageLayer(layer)
        # The template's own expression: the SDK's runs name the files itself,
        # so this is only what the layout manager stores.
        atlas.setFilenameExpression("'sheet-' || @atlas_featureid")
        atlas.setEnabled(True)
        # The template is saved from a layout of its own name and the layout is
        # removed again, so loading the file adds that name to the project.
        existing = manager.layoutByName(TEMPLATE_LAYOUT)
        if existing is not None:
            manager.removeLayout(existing)
        source = QgsPrintLayout(QgsProject.instance())
        source.initializeDefaults()
        source.setName(TEMPLATE_LAYOUT)
        if not source.saveAsTemplate(str(template_file()), QgsReadWriteContext()):
            pytest.fail("the layout template fixture could not be written")

    def drive_layouts() -> None:
        service = layouts.jobs
        service.tick()
        layout_workers.run_all()
        service.tick()

    # A canvas for the canvas contract: real, offscreen, and sized, because a
    # canvas with no output size reports no scale at all.
    native_canvas = _offscreen_canvas()
    canvas = NativeCanvas(scope, layers=layers, canvas=native_canvas)

    # A layer the features tests ask for is opened when they ask: this backend
    # starts with nothing open, which is a fact the algorithms contract asserts.
    opened: dict[str, str] = {}

    def _open(source: Path) -> str:
        if str(source) not in opened:
            opened[str(source)] = layers.open_vector(source).id
        return opened[str(source)]

    def fixture_layer() -> str:
        return _open(FIXTURE_DATASET)

    editable_copy = _feature_work_directory() / "editable.geojson"
    shutil.copyfile(FIXTURE_DATASET, editable_copy)

    def editable_layer() -> str:
        return _open(editable_copy)

    return Services(
        canvas=canvas,
        draw=lambda shape: _draw_on(native_canvas, shape),
        is_drawing=lambda: _is_drawing(native_canvas),
        declare_theme=lambda name: _declare_theme(name),
        files=files,
        features=features,
        editable_layer=editable_layer,
        editable_dataset=editable_copy,
        fixture_layer=fixture_layer,
        algorithms=algorithms,
        model_file=model_file,
        drive_algorithms=drive_algorithms,
        algorithm_work_items=lambda: tuple(algo_workers.items),
        layers=layers,
        rasters=rasters,
        layouts=layouts,
        declare_layouts=declare_layouts,
        drive_layouts=drive_layouts,
        layout_work_items=lambda: tuple(layout_workers.items),
        layout_directory=lambda: layout_directory,
        layout_template=template_file,
        open_raster=open_raster,
        raster_dataset=raster_file,
        open_mesh=open_mesh,
        mesh_dataset=MESH_DATASET,
        open_annotation=open_annotation,
        open_point_cloud=open_point_cloud,
        point_cloud_dataset=point_cloud_file,
        open_vector_tile=open_vector_tile,
        vector_tile_dataset=vector_tile_file,
        open_tiled_scene=open_tiled_scene,
        tiled_scene_dataset=tiled_scene_file,
        project=project,
        project_directory=lambda: project_directory,
        declare_groups=declare_groups,
        # A per-session prefix keeps the run out of the real profile's keys and
        # keeps one test's values out of the next one's.
        settings=NativeSettings(scope, prefix=f"qgis-sdk-contract/{_SESSION_TOKEN}"),
        styles=styles,
        connections=connections,
        declare_auth_configuration=declare_auth_configuration,
        postgis_connection=postgis_connection,
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


#: The canvases this session built. QgsMapCanvas is a plain QObject owned by
#: Python here, so a reference has to outlive the test that used it.
_CANVASES: list[object] = []


def _offscreen_canvas():
    """A sized ``QgsMapCanvas`` on the fixture CRS, for the native contract."""
    from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle
    from qgis.gui import QgsMapCanvas

    canvas = QgsMapCanvas()
    canvas.resize(800, 600)
    canvas.setDestinationCrs(QgsCoordinateReferenceSystem(FIXTURE_CRS))
    canvas.setExtent(
        QgsRectangle(
            FIXTURE_EXTENT.x_min,
            FIXTURE_EXTENT.y_min,
            FIXTURE_EXTENT.x_max,
            FIXTURE_EXTENT.y_max,
        )
    )
    _CANVASES.append(canvas)
    return canvas


def _forget_project_file(project: object) -> None:
    """Start the shared project from nothing, file name included.

    ``clear()`` is what QGIS's own "New project" does: it drops the layers, the
    properties, the variables, the bookmarks *and* the file name, so a test that
    reads or saves cannot answer with what the previous test wrote. A build that
    keeps ``clear()`` away falls back to clearing the name alone, and failing
    both is not fatal: it only means the tests share a file name, which is what
    the contract refuses to assume either way.
    """
    clear = getattr(project, "clear", None)
    if clear is not None:
        try:
            clear()
            return
        except (TypeError, RuntimeError):  # pragma: no cover - signature drift
            pass
    setter = getattr(project, "setFileName", None)
    if setter is None:  # pragma: no cover - a build that keeps it protected
        return
    try:
        setter("")
    except (TypeError, RuntimeError):  # pragma: no cover - signature drift
        return


def _left_button():
    """The left mouse button, spelled for the binding this QGIS uses."""
    from qgis.PyQt.QtCore import Qt

    return getattr(Qt, "MouseButton", Qt).LeftButton


#: The clicks a user makes to draw each shape, in canvas coordinates: a point is
#: one click, a line ends on a repeated click, and a polygon closes on its first
#: vertex - the gestures the capture tool documents.
_DRAWN_POINTS: dict[str, list[tuple[float, float]]] = {
    "point": [(21.1, 52.1)],
    "line": [(21.0, 52.0), (21.2, 52.2), (21.2, 52.2)],
    "polygon": [(21.0, 52.0), (21.2, 52.0), (21.2, 52.2), (21.0, 52.0)],
}


def _draw_on(canvas, shape: str) -> None:
    """Click ``shape`` onto the canvas, as the user of a capture tool would.

    The tool is reached through the canvas rather than through the adapter, so
    this drives the same object QGIS would hand a click to.
    """
    from qgis.core import QgsPointXY
    from qgis_sdk.adapters.qgis.canvas import _CaptureTool

    tool = canvas.mapTool()
    if not isinstance(tool, _CaptureTool):
        pytest.fail("no capture tool is installed on the canvas")
    for x, y in _DRAWN_POINTS[shape]:
        tool.canvasClicked(QgsPointXY(x, y), _left_button())


def _is_drawing(canvas) -> bool:
    """Whether a capture tool is installed, i.e. a drawing is in progress."""
    from qgis_sdk.adapters.qgis.canvas import _CaptureTool

    return isinstance(canvas.mapTool(), _CaptureTool)


def _declare_theme(name: str) -> None:
    """Insert one map theme over the project's layers.

    A theme is a record in the project's collection; the canvas only ever picks
    one, so this is the test's job and not the adapter's.
    """
    from qgis.core import QgsMapThemeCollection, QgsProject

    record = QgsMapThemeCollection.MapThemeRecord()
    for layer in QgsProject.instance().mapLayers().values():
        record.addLayerRecord(QgsMapThemeCollection.MapThemeLayerRecord(layer))
    QgsProject.instance().mapThemeCollection().insert(name, record)


BACKENDS: dict[str, Callable[[], Services]] = {"fake": _fake_services}
if _native_available():
    BACKENDS["native"] = _native_services


def _backend_params() -> list[object]:
    return [
        pytest.param(name, marks=pytest.mark.qgis) if name == "native" else name
        for name in sorted(BACKENDS)
    ]


@pytest.fixture(params=_backend_params())
def services(request: pytest.FixtureRequest) -> Services:
    """Run the calling contract test against every registered backend."""
    return BACKENDS[request.param]()


@pytest.fixture(scope="session", autouse=True)
def _remove_native_outputs_after_the_session() -> object:
    """Remove the native backend's temporary outputs; QGIS itself is stopped
    by the session fixture in ``tests/conftest.py``."""
    yield
    shutil.rmtree(_WORK_ROOT, ignore_errors=True)


@pytest.fixture
def native_services() -> Services:
    """Build the native backend, skipping when QGIS is not opted in."""
    if "native" not in BACKENDS:
        pytest.skip(f"set {NATIVE_ENV_FLAG}=1 with QGIS installed for native checks")
    return BACKENDS["native"]()
