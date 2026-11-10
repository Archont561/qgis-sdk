"""Steps for the raster, project and layout features.

The features describe a backend the way a plugin author meets it - open,
describe, sample, measure, edit the tree, export a print layout - so the worlds
here are built from the SDK's own fakes: the same objects a plugin's pure tests
construct. Each scenario gets a fresh world, which is what makes the numbers it
asserts the numbers of one grid rather than of whatever ran before it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    Bookmark,
    CanvasExtent,
    CanvasPoint,
    LayerNode,
    LayerTree,
    ProjectChange,
    QgisSdkBookmarkNotFoundError,
    QgisSdkLayerNotFoundError,
    RasterLayerInfo,
    RasterSample,
    RasterStatistics,
    VectorLayerInfo,
)
from qgis_sdk.testing import (
    FakeFiles,
    FakeLayers,
    FakeLayouts,
    FakeProject,
    FakeRasters,
    FakeWorkers,
    VectorLayerDeclaration,
)

REFERENCE = Path(__file__).resolve().parent / "fixtures" / "reference"
GRID = REFERENCE / "elevation.asc"
POINTS = REFERENCE / "points.geojson"
GRID_CRS = "EPSG:4326"
WORKING_CRS = "EPSG:3857"


@dataclass
class RasterWorld:
    """The fake runtime the raster scenarios arrange and observe."""

    scope: ResourceScope
    rasters: FakeRasters
    layers: FakeLayers
    project: FakeProject
    vector: VectorLayerInfo | None = None
    opened: RasterLayerInfo | None = None
    samples: dict[str, RasterSample] = field(default_factory=dict)
    statistics: RasterStatistics | None = None
    refusal: Exception | None = None


@dataclass
class ProjectWorld:
    """The fake runtime the project scenarios arrange and observe."""

    scope: ResourceScope
    layers: FakeLayers
    project: FakeProject
    tree: LayerTree | None = None
    written: LayerTree | None = None
    layer: VectorLayerInfo | None = None
    frames: list[ProjectChange] = field(default_factory=list)
    bookmark: Bookmark | None = None
    refusal: Exception | None = None


def _open_points(layers: FakeLayers) -> VectorLayerInfo:
    """Open the checked-in points dataset, registered on this fake."""
    layers.register(
        VectorLayerDeclaration(
            POINTS, name="points", geometry_type="point", field_names=("id", "value")
        )
    )
    return layers.open_vector(POINTS)


def _project_world() -> ProjectWorld:
    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        VectorLayerDeclaration(
            POINTS, name="points", geometry_type="point", field_names=("id", "value")
        )
    )
    return ProjectWorld(scope=scope, layers=layers, project=FakeProject(layers, scope))


def _group_id(world: ProjectWorld, name: str) -> str:
    """The id the tree gave the group with ``name``.

    The id is the backend's to choose, so the feature speaks in names and this
    helper asks the tree which id that name is.
    """
    for node in world.project.layer_tree().nodes:
        if node.kind == "group" and node.name == name:
            return node.id
    raise AssertionError(f"no group named {name!r} in this project")


def _nested_groups(world: ProjectWorld, outer: str, inner: str) -> None:
    """Declare the two nested groups, named the way a tree names them."""
    outer_id = f"group:{outer}"
    world.tree = world.project.set_tree(
        [
            LayerNode(id=outer_id, name=outer, kind="group"),
            LayerNode(
                id=f"{outer_id}/{inner}", name=inner, kind="group", parent=outer_id
            ),
        ]
    )


# -- the raster world --------------------------------------------------------


@given(
    "a runtime with the raster backend and the three-by-two grid",
    target_fixture="raster_world",
)
def raster_runtime() -> RasterWorld:
    """One fake runtime holding the grid the SDK's own contract tests read."""
    scope = ResourceScope()
    rasters = FakeRasters(scope)
    rasters.register(
        GRID,
        name="elevation",
        extent=CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2),
        data_types=("Float64",),
        no_data=(-9999.0,),
        resolution=(0.1, 0.1),
        crs=GRID_CRS,
        values=(1.0,),
        holes=((21.15, 52.05),),
        statistics={
            1: RasterStatistics(
                band=1,
                minimum=1.0,
                maximum=6.0,
                mean=3.2,
                std_dev=1.9235384061671346,
                valid_count=5,
                no_data_count=1,
            )
        },
    )
    layers = FakeLayers(scope, rasters=rasters)
    return RasterWorld(
        scope=scope,
        rasters=rasters,
        layers=layers,
        project=FakeProject(layers, scope),
    )


@given(parsers.parse('the vector layer "{name}" is open in the project'))
def vector_layer_open(raster_world: RasterWorld, name: str) -> None:
    """Open the points fixture under the name the scenario says, and add it."""
    assert name == "points", name
    raster_world.vector = _open_points(raster_world.layers)
    raster_world.project.add_layer(raster_world.vector.id)


@given("the plugin opens the bundled elevation grid")
@when("the plugin opens the bundled elevation grid")
def open_grid(raster_world: RasterWorld) -> None:
    """A raster is a layer too: open it, then present it on the project."""
    info = raster_world.rasters.open_raster(GRID)
    raster_world.project.add_layer(info.id)
    raster_world.opened = info


@then("the raster backend describes one Float64 band")
def described_band(raster_world: RasterWorld) -> None:
    assert raster_world.opened is not None
    opened = raster_world.rasters.raster(raster_world.opened.id)

    assert (opened.kind, opened.band_count) == ("raster", 1)
    assert opened.data_types == ("Float64",)


@then(parsers.parse("the grid's no-data value is {value}"))
def no_data_value(raster_world: RasterWorld, value: str) -> None:
    assert raster_world.opened is not None
    opened = raster_world.rasters.raster(raster_world.opened.id)

    assert opened.no_data == (float(value),)


@then("the layers service lists a vector and a raster, in that order")
def listed_beside_the_vector(raster_world: RasterWorld) -> None:
    kinds = [layer.kind for layer in raster_world.layers.list_layers()]

    assert kinds == ["vector", "raster"]


@when(parsers.parse("the grid is sampled at {x} east and {y} north"))
def sample_grid(raster_world: RasterWorld, x: str, y: str) -> None:
    assert raster_world.opened is not None
    raster_world.samples["point"] = raster_world.rasters.sample(
        raster_world.opened.id, CanvasPoint(x=float(x), y=float(y))
    )


@then(parsers.parse("the sample answers {value} in band 1"))
def sample_value(raster_world: RasterWorld, value: str) -> None:
    sample = raster_world.samples["point"]

    assert sample.values == pytest.approx((float(value),))


@then("the sample reports the raster's own CRS")
def sample_crs(raster_world: RasterWorld) -> None:
    sample = raster_world.samples["point"]

    assert sample.point.crs == GRID_CRS


@then("the sample answers no value")
def sample_no_value(raster_world: RasterWorld) -> None:
    sample = raster_world.samples["point"]

    assert sample.values == (None,)


@when("band 1 is measured")
def measure_band(raster_world: RasterWorld) -> None:
    assert raster_world.opened is not None
    raster_world.statistics = raster_world.rasters.statistics(raster_world.opened.id, 1)


@then(
    parsers.parse(
        "the statistics report {valid:d} valid cells and {empty:d} no-data cell"
    )
)
def statistics_counts(raster_world: RasterWorld, valid: int, empty: int) -> None:
    statistics = raster_world.statistics
    assert statistics is not None

    assert (statistics.valid_count, statistics.no_data_count) == (valid, empty)


@then(parsers.parse("the statistics report a mean of {mean}"))
def statistics_mean(raster_world: RasterWorld, mean: str) -> None:
    statistics = raster_world.statistics
    assert statistics is not None

    assert statistics.mean == pytest.approx(float(mean))


@when("the vector layer's id is sampled as a raster")
def sample_a_vector(raster_world: RasterWorld) -> None:
    assert raster_world.vector is not None
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        raster_world.rasters.sample(
            raster_world.vector.id, CanvasPoint(x=21.05, y=52.15)
        )
    raster_world.refusal = error.value


@then("the SDK refuses it as a missing raster layer")
def refused_as_a_raster(raster_world: RasterWorld) -> None:
    assert isinstance(raster_world.refusal, QgisSdkLayerNotFoundError)
    assert raster_world.vector is not None
    assert raster_world.refusal.identifier == raster_world.vector.id


# -- the project world -------------------------------------------------------


@given("a project with no CRS", target_fixture="project_world")
def bare_project() -> ProjectWorld:
    """A project as `qgis-sdk new` leaves one: nothing in it, no CRS."""
    return _project_world()


@given(
    parsers.parse('a project with the nested group "{outer}" holding "{inner}"'),
    target_fixture="project_world",
)
def nested_project(outer: str, inner: str) -> ProjectWorld:
    """A project whose tree is already two groups deep, as an opened one is."""
    world = _project_world()
    _nested_groups(world, outer, inner)
    return world


@given("a vector layer the runtime owns")
def owned_vector(project_world: ProjectWorld) -> None:
    project_world.layer = _open_points(project_world.layers)


@when(parsers.parse('the project\'s CRS is set to "{auth_id}"'))
def set_project_crs(project_world: ProjectWorld, auth_id: str) -> None:
    project_world.project.set_crs(auth_id)


@then(parsers.parse('the project reports "{auth_id}"'))
def project_crs(project_world: ProjectWorld, auth_id: str) -> None:
    assert project_world.project.crs() == auth_id


@when("the project is written to its file and read back")
def write_and_read(tmp_path: Path, project_world: ProjectWorld) -> None:
    assert project_world.tree is not None
    project_world.written = project_world.tree
    destination = tmp_path / "project.qgs"
    project_world.project.write(destination)
    project_world.tree = project_world.project.read(destination)


@then("the tree is the one that was written, nesting and order included")
def round_tripped_tree(project_world: ProjectWorld) -> None:
    assert project_world.written is not None
    assert project_world.tree == project_world.written
    assert [node.id for node in project_world.tree.nodes] == [
        node.id for node in project_world.written.nodes
    ]


@when(parsers.parse('the group "{name}" is hidden'))
def hide_group(project_world: ProjectWorld, name: str) -> None:
    project_world.project.set_visible(_group_id(project_world, name), False)
    project_world.tree = project_world.project.layer_tree()


@then(parsers.parse('"{hidden}" is not visible and "{shown}" still is'))
def own_visibility(project_world: ProjectWorld, hidden: str, shown: str) -> None:
    assert project_world.tree is not None

    assert project_world.tree.node(_group_id(project_world, hidden)).visible is False
    # Hiding a group hides what it holds without rewriting every child.
    assert project_world.tree.node(_group_id(project_world, shown)).visible is True


@when(parsers.parse('that layer is added into the group "{name}"'))
def add_into_group(project_world: ProjectWorld, name: str) -> None:
    assert project_world.layer is not None
    project_world.tree = project_world.project.add_layer(
        project_world.layer.id, group=_group_id(project_world, name)
    )


@then(parsers.parse('the tree holds the layer inside "{name}"'))
def layer_inside_group(project_world: ProjectWorld, name: str) -> None:
    assert project_world.tree is not None and project_world.layer is not None
    tree = project_world.tree
    parent = _group_id(project_world, name)

    assert tree.node(project_world.layer.id).parent == parent
    assert [node.id for node in tree.children_of(parent)] == [project_world.layer.id]


@when(parsers.parse('the variable "{key}" is set to "{value}"'))
def set_variable(project_world: ProjectWorld, key: str, value: str) -> None:
    project_world.project.set_variable(key, value)


@when(parsers.parse('the variable "{key}" is unset'))
def unset_variable(project_world: ProjectWorld, key: str) -> None:
    project_world.project.unset_variable(key)


@when(parsers.parse('the custom property "{key}" is set to "{value}"'))
def set_custom_property(project_world: ProjectWorld, key: str, value: str) -> None:
    project_world.project.set_custom_property(key, value)


@then(parsers.parse('the variables report "{key}" as "{value}"'))
def variables_report(project_world: ProjectWorld, key: str, value: str) -> None:
    entries = {entry.key: entry.value for entry in project_world.project.variables()}

    assert entries.get(key) == value


@then(parsers.parse('the custom properties report "{key}" as "{value}"'))
def properties_report(project_world: ProjectWorld, key: str, value: str) -> None:
    entries = {
        entry.key: entry.value for entry in project_world.project.custom_properties()
    }

    assert entries.get(key) == value


@then("the variables name no entry")
def variables_empty(project_world: ProjectWorld) -> None:
    assert project_world.project.variables() == ()


@when(
    parsers.parse(
        'the bookmark "{name}" is added over {x_min}, {y_min}, {x_max}, {y_max}'
    )
)
def add_bookmark(
    project_world: ProjectWorld,
    name: str,
    x_min: str,
    y_min: str,
    x_max: str,
    y_max: str,
) -> None:
    project_world.project.add_bookmark(
        name,
        CanvasExtent(
            x_min=float(x_min),
            y_min=float(y_min),
            x_max=float(x_max),
            y_max=float(y_max),
        ),
    )
    project_world.bookmark = project_world.project.bookmark(name)


@then(parsers.parse('the bookmark "{name}" covers that box'))
def bookmark_box(project_world: ProjectWorld, name: str) -> None:
    bookmark = project_world.project.bookmark(name)

    assert bookmark.name == name
    assert bookmark.extent == CanvasExtent(
        x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2
    )


@when(parsers.parse('the bookmark "{name}" is read'))
def read_bookmark(project_world: ProjectWorld, name: str) -> None:
    with pytest.raises(QgisSdkBookmarkNotFoundError) as error:
        project_world.project.bookmark(name)
    project_world.refusal = error.value


@then("the SDK refuses it as a missing bookmark")
def refused_as_a_bookmark(project_world: ProjectWorld) -> None:
    assert isinstance(project_world.refusal, QgisSdkBookmarkNotFoundError)


@given("the project's changes are being watched")
def watch_changes(project_world: ProjectWorld) -> None:
    project_world.project.watch_changes(project_world.frames.append)


@then(parsers.parse("the stream delivered {kinds}"))
def stream_order(project_world: ProjectWorld, kinds: str) -> None:
    expected = kinds.replace(" then ", " ").split()

    assert [frame.kind for frame in project_world.frames] == expected


# -- print layouts (TASK-89) -----------------------------------------------------

#: The three reference points, in the order the fixture stores them: the ids an
#: atlas iterates are the feature ids the file gave the rows.
ATLAS_FEATURES = (1, 2, 3)


@dataclass
class LayoutWorld:
    """The fake runtime the layout scenarios arrange and observe."""

    scope: ResourceScope
    layouts: FakeLayouts
    files: FakeFiles
    workers: FakeWorkers
    directory: Path
    listed: tuple = ()
    handle: object | None = None
    export: object | None = None
    atlas: object | None = None
    refusal: Exception | None = None
    progress: list[float] = field(default_factory=list)
    destination: Path | None = None
    template: Path | None = None
    #: The one-page layout the background declared, by name.
    single_page_layout: str = ""
    #: The file's timestamp before a replacing export, for the overwrite Then.
    replaced_from: int = 0

    def drive(self) -> None:
        """One round trip through the layouts service's own job service."""
        service = self.layouts.jobs
        service.tick()
        self.workers.run_all()
        service.tick()

    def info(self, name: str):
        """The description of one declared layout, by name."""
        for entry in self.layouts.list():
            if entry.name == name:
                return entry
        raise AssertionError(f"the project holds no layout called {name!r}")


@given(
    parsers.parse('a runtime with the layout backend and a one-page layout "{name}"'),
    target_fixture="layout_world",
)
def layout_runtime(tmp_path: Path, name: str) -> LayoutWorld:
    scope = ResourceScope()
    workers = FakeWorkers()
    files = FakeFiles(scope, owner="plugin:feature")
    directory = tmp_path / "exports"
    directory.mkdir()
    layouts = FakeLayouts(
        scope, workers=workers, files=files, working_directory=directory
    )
    layouts.declare_layout(name)
    return LayoutWorld(
        scope=scope,
        layouts=layouts,
        files=files,
        workers=workers,
        directory=directory,
        single_page_layout=name,
    )


@given(parsers.parse('the project holds a two-page layout "{name}"'))
def declare_layout(layout_world: LayoutWorld, name: str) -> None:
    layout_world.layouts.declare_layout(name, pages=2)


@given(
    parsers.parse('the project holds an atlas "{name}" over the three reference points')
)
def declare_atlas(layout_world: LayoutWorld, name: str) -> None:
    layout_world.layouts.declare_atlas(
        name, coverage_layer="points", feature_ids=ATLAS_FEATURES
    )


@when("the plugin lists the print layouts")
def list_layouts(layout_world: LayoutWorld) -> None:
    layout_world.listed = layout_world.layouts.list()


@then(parsers.parse('the project reports "{name}" with {pages:d} page and no atlas'))
@then(parsers.parse('the project reports "{name}" with {pages:d} pages and no atlas'))
def described_layout(layout_world: LayoutWorld, name: str, pages: int) -> None:
    assert layout_world.listed, "the plugin has not listed the layouts yet"
    described = {entry.name: entry for entry in layout_world.listed}

    assert name in described
    assert described[name].id == name
    assert described[name].page_count == pages
    assert described[name].atlas is None


@then(parsers.parse('the project reports "{name}" with a coverage layer'))
def described_atlas(layout_world: LayoutWorld, name: str) -> None:
    described = {entry.name: entry for entry in layout_world.listed}
    atlas = described[name].atlas

    assert atlas is not None
    assert atlas.enabled is True
    assert atlas.coverage_layer == "points"


@given(parsers.parse('the plugin exports "{name}" as a {format}'))
@when(parsers.parse('the plugin exports "{name}" as a {format}'))
def export_layout(layout_world: LayoutWorld, name: str, format: str) -> None:
    try:
        layout_world.handle = layout_world.layouts.export(name, format=format.lower())
    except Exception as error:  # noqa: BLE001 - the refusal is what a Then asserts
        layout_world.refusal = error


@when(
    parsers.parse('the plugin exports "{name}" as a {format} and watches its progress')
)
def export_layout_and_watch(layout_world: LayoutWorld, name: str, format: str) -> None:
    handle = layout_world.layouts.export(name, format=format.lower())
    handle.on_progress(layout_world.progress.append)
    layout_world.handle = handle


@then("the export has not started")
def export_not_started(layout_world: LayoutWorld) -> None:
    from qgis_sdk.jobs import JobStatus

    assert layout_world.handle is not None
    assert layout_world.handle.status is JobStatus.QUEUED


@when("the job is driven to its end")
def drive_job(layout_world: LayoutWorld) -> None:
    layout_world.drive()


@then(parsers.parse("the job succeeded with a {format} of {pages:d} pages"))
def job_succeeded(layout_world: LayoutWorld, format: str, pages: int) -> None:
    from qgis_sdk.jobs import JobStatus

    assert layout_world.handle is not None
    assert layout_world.handle.status is JobStatus.SUCCEEDED
    export = layout_world.handle.result
    layout_world.export = export

    assert export.format == format.lower()
    assert export.pages == pages
    assert export.bytes > 0
    assert Path(export.path).is_file()


@then("the exported file is inside the host's output directory")
def exported_inside_directory(layout_world: LayoutWorld) -> None:
    assert layout_world.export is not None
    written = Path(layout_world.export.path)

    assert written.parent == layout_world.directory
    assert written.suffix == ".pdf"


@then("the progress ends at 1.0 and never went backwards")
def progress_reached_the_end(layout_world: LayoutWorld) -> None:
    seen = layout_world.progress

    assert seen, "an export that produced a file reported no progress"
    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(1.0)


@when("the export is cancelled before its body runs")
def cancel_export(layout_world: LayoutWorld) -> None:
    assert layout_world.handle is not None
    assert layout_world.handle.cancel() is True


@then("the job is cancelled and no PDF was written")
def cancelled_without_a_file(layout_world: LayoutWorld) -> None:
    from qgis_sdk.jobs import JobStatus
    from qgis_sdk.models import QgisSdkJobCancelledError

    assert layout_world.handle is not None
    assert layout_world.handle.status is JobStatus.CANCELLED
    with pytest.raises(QgisSdkJobCancelledError):
        _ = layout_world.handle.result
    assert not list(layout_world.directory.glob("report*.pdf"))


@then(parsers.parse("the export is a {format} of {pages:d} page"))
@then(parsers.parse("the export is a {format} of {pages:d} pages"))
def exported_as(layout_world: LayoutWorld, format: str, pages: int) -> None:
    assert layout_world.handle is not None
    export = layout_world.handle.result
    layout_world.export = export

    assert export.format == format.lower()
    assert export.pages == pages
    assert Path(export.path).suffix == ".png"
    assert Path(export.path).is_file()


@when(parsers.parse('the plugin exports "{name}" to a path it typed'))
def export_to_a_path(layout_world: LayoutWorld, name: str) -> None:
    typed = layout_world.directory / "typed-by-hand.pdf"
    layout_world.destination = typed
    try:
        layout_world.layouts.render(name, destination=str(typed))
    except Exception as error:  # noqa: BLE001 - the refusal is what a Then asserts
        layout_world.refusal = error


@when(parsers.parse('the plugin exports "{name}" to a ref the host minted'))
@given(parsers.parse('"{name}" was exported to a ref the host minted'))
def export_to_a_ref(layout_world: LayoutWorld, name: str) -> None:
    destination = layout_world.directory / f"{name}-granted.pdf"
    ref = layout_world.files.grant_file(
        destination, operations=("write",), overwrite=True
    )
    layout_world.destination = destination
    try:
        # The blocking form: the scenario is about where the file landed, and a
        # job would need its own "driven to its end" step in between.
        layout_world.export = layout_world.layouts.render(name, destination=ref)
    except Exception as error:  # noqa: BLE001 - a refusal is what a Then asserts
        layout_world.refusal = error


@then("the SDK refuses the destination as not a ref")
def refused_as_not_a_ref(layout_world: LayoutWorld) -> None:
    from qgis_sdk.models import QgisSdkExportRefusedError

    assert isinstance(layout_world.refusal, QgisSdkExportRefusedError)
    assert "FileRef" in str(layout_world.refusal)
    assert layout_world.destination is not None
    assert not layout_world.destination.exists()


@then("the export landed where the ref named")
def landed_where_the_ref_named(layout_world: LayoutWorld) -> None:
    assert layout_world.export is not None

    assert layout_world.destination is not None
    assert layout_world.export.path == str(layout_world.destination)
    assert layout_world.destination.is_file()


@when("the same ref is exported to again")
def export_to_the_same_ref(layout_world: LayoutWorld) -> None:
    layout_world.refusal = None
    assert layout_world.destination is not None
    ref = layout_world.files.grant_file(
        layout_world.destination, operations=("write",), overwrite=True
    )
    try:
        layout_world.layouts.render("report", destination=ref)
    except Exception as error:  # noqa: BLE001 - the refusal is what a Then asserts
        layout_world.refusal = error


@then("the SDK refuses the destination as existing")
def refused_as_existing(layout_world: LayoutWorld) -> None:
    from qgis_sdk.models import QgisSdkExportRefusedError

    assert isinstance(layout_world.refusal, QgisSdkExportRefusedError)
    assert "overwrite" in str(layout_world.refusal)


@when("the same ref is exported to with overwrite")
def export_with_overwrite(layout_world: LayoutWorld) -> None:
    assert layout_world.destination is not None
    before = layout_world.destination.stat().st_mtime_ns
    ref = layout_world.files.grant_file(
        layout_world.destination, operations=("write",), overwrite=True
    )
    layout_world.export = layout_world.layouts.render(
        "report", destination=ref, overwrite=True
    )
    layout_world.replaced_from = before


@then("the export replaced the file")
def replaced_the_file(layout_world: LayoutWorld) -> None:
    assert layout_world.export is not None
    assert layout_world.destination is not None
    assert layout_world.export.path == str(layout_world.destination)
    assert layout_world.destination.stat().st_mtime_ns >= layout_world.replaced_from


@when(parsers.parse('the atlas "{name}" is run with the pattern "{pattern}"'))
def run_atlas_with_pattern(layout_world: LayoutWorld, name: str, pattern: str) -> None:
    try:
        layout_world.atlas = layout_world.layouts.render_atlas(name, pattern=pattern)
    except Exception as error:  # noqa: BLE001 - the refusal is what a Then asserts
        layout_world.refusal = error


@when(parsers.parse('the atlas "{name}" is run'))
def run_atlas(layout_world: LayoutWorld, name: str) -> None:
    try:
        layout_world.atlas = layout_world.layouts.render_atlas(name)
    except Exception as error:  # noqa: BLE001 - the refusal is what a Then asserts
        layout_world.refusal = error


@then(parsers.parse("the atlas wrote {count:d} files, one for each feature"))
def atlas_files(layout_world: LayoutWorld, count: int) -> None:
    assert layout_world.atlas is not None
    run = layout_world.atlas

    assert len(run.pages) == count
    assert tuple(page.feature_id for page in run.pages) == ATLAS_FEATURES
    assert tuple(page.index for page in run.pages) == (1, 2, 3)
    for page in run.pages:
        assert Path(page.path).is_file()


@then("the file names are the ones the pattern asks for")
def atlas_names(layout_world: LayoutWorld) -> None:
    assert layout_world.atlas is not None

    for page in layout_world.atlas.pages:
        assert Path(page.path).name == (f"sheet-{page.index:02d}-{page.feature_id}.pdf")


@then(parsers.parse('the SDK refuses the pattern\'s unknown field "{field}"'))
def refused_pattern_field(layout_world: LayoutWorld, field: str) -> None:
    from qgis_sdk.models import QgisSdkExportRefusedError

    assert isinstance(layout_world.refusal, QgisSdkExportRefusedError)
    assert field in str(layout_world.refusal)


@then("the SDK refuses the atlas as missing")
def refused_missing_atlas(layout_world: LayoutWorld) -> None:
    from qgis_sdk.models import QgisSdkExportRefusedError

    assert isinstance(layout_world.refusal, QgisSdkExportRefusedError)
    assert "no atlas" in str(layout_world.refusal)


@then("the SDK refuses the destination as holding more than one page")
def refused_multi_page_image(layout_world: LayoutWorld) -> None:
    from qgis_sdk.models import QgisSdkExportRefusedError

    assert isinstance(layout_world.refusal, QgisSdkExportRefusedError)
    assert "one page" in str(layout_world.refusal)


@when(parsers.parse('the plugin loads the template "{filename}"'))
def load_template(layout_world: LayoutWorld, filename: str) -> None:
    template = layout_world.directory / filename
    template.write_text("<!-- the fake only has to find the template -->")
    layout_world.template = template
    layout_world.listed = (
        layout_world.layouts.load_template(
            layout_world.files.grant_file(template, operations=("read",))
        ),
    )


@when("the plugin loads the template as a path it typed")
def load_template_as_a_path(layout_world: LayoutWorld) -> None:
    template = layout_world.directory / "templated.qpt"
    template.write_text("<!-- the fake only has to find the template -->")
    layout_world.template = template
    try:
        layout_world.layouts.load_template(template)
    except Exception as error:  # noqa: BLE001 - the refusal is what a Then asserts
        layout_world.refusal = error


@then("the SDK refuses the template as not a ref")
def refused_template_as_path(layout_world: LayoutWorld) -> None:
    from qgis_sdk.models import QgisSdkExportRefusedError

    assert isinstance(layout_world.refusal, QgisSdkExportRefusedError)
    assert "FileRef" in str(layout_world.refusal)
