"""Contract: print layouts and atlases, on the layouts both backends declare.

The fixture is the project's layout manager: a two-page layout called
``report``, a one-page ``cover``, an ``atlas`` over the three reference points,
and a ``.qpt`` template saved from a layout of its own name. The fake declares
the same four things, so every assertion here is a statement about *both*
backends or about neither - including the fact that a PNG of a two-page layout
is refused while the PDF of it holds both pages.

The export is a job (TASK-89). The service owns the job service it submits
through, so a test drives it in the three moves the job contract documents:
``tick`` submits, the worker runs the body, ``tick`` delivers. On the native
backend the body is a real offscreen ``QgsLayoutExporter`` run; the only thing
faked there is *when* the worker runs it, because an export needs no Qt event
loop of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.jobs import JobStatus
from qgis_sdk.models import (
    QgisSdkExportRefusedError,
    QgisSdkJobCancelledError,
    QgisSdkLayoutNotFoundError,
)
from qgis_sdk.services import Layouts

if TYPE_CHECKING:
    Services = conftest.Services

pytestmark = pytest.mark.usefixtures("services")


def _layouts(services: Services) -> Layouts:
    """The backend's layouts service, with the contract's layouts declared."""
    layouts = services.layouts
    assert layouts is not None, "this backend has not joined the layouts contract"
    assert services.declare_layouts is not None
    services.declare_layouts()
    return layouts


def _drive(services: Services) -> None:
    """Submit, run the body, deliver: one round trip of the layouts job service."""
    assert services.drive_layouts is not None
    services.drive_layouts()


def _directory(services: Services):
    assert services.layout_directory is not None
    return services.layout_directory()


# -- listing and templates ------------------------------------------------------


def test_nothing_is_declared_before_the_layouts_are(services: Services) -> None:
    """A project with no layouts lists none: the fake answers what QGIS answers."""
    layouts = services.layouts
    assert layouts is not None
    assert layouts.list() == ()


def test_the_project_describes_the_layouts_it_holds(services: Services) -> None:
    layouts = _layouts(services)

    described = {info.name: info for info in layouts.list()}

    assert set(described) == {
        conftest.LAYOUT_NAME,
        conftest.SINGLE_PAGE_LAYOUT,
        conftest.ATLAS_NAME,
    }
    report = described[conftest.LAYOUT_NAME]
    # A layout is named by its own name, so the id is that name.
    assert report.id == conftest.LAYOUT_NAME
    assert report.page_count == conftest.LAYOUT_PAGES
    assert report.atlas is None


def test_an_atlas_layout_reports_its_coverage(services: Services) -> None:
    layouts = _layouts(services)

    atlas = {info.name: info for info in layouts.list()}[conftest.ATLAS_NAME]

    assert atlas.atlas is not None
    assert atlas.atlas.enabled is True
    assert atlas.atlas.coverage_layer == conftest.FIXTURE_NAME
    # The layout manager's own file-name expression; the SDK names the files
    # itself, so this is a fact about the layout, not about a render.
    assert atlas.atlas.filename_expression


def test_a_template_adds_a_layout_named_after_the_file(services: Services) -> None:
    layouts = _layouts(services)
    assert services.files is not None
    assert services.layout_template is not None

    info = layouts.load_template(services.files.grant_file(services.layout_template()))

    assert info.name == conftest.TEMPLATE_LAYOUT
    assert info.page_count == 1
    assert conftest.TEMPLATE_LAYOUT in {entry.name for entry in layouts.list()}


def test_a_template_is_a_ref_not_a_path(services: Services) -> None:
    layouts = _layouts(services)
    assert services.layout_template is not None

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.load_template(services.layout_template())

    assert "FileRef" in str(refused.value)


# -- one export, as a job --------------------------------------------------------


def test_a_pdf_export_runs_as_a_job_and_writes_every_page(services: Services) -> None:
    layouts = _layouts(services)

    handle = layouts.export(conftest.LAYOUT_NAME)
    # Submitting starts nothing: the body runs on the worker, submitted by a tick.
    assert handle.status is JobStatus.QUEUED
    assert handle.description.title == f"Export layout {conftest.LAYOUT_NAME!r}"

    _drive(services)
    export = handle.result

    assert export.format == "pdf"
    assert export.pages == conftest.LAYOUT_PAGES
    assert export.bytes > 0
    written = conftest.Path(export.path)
    assert written.suffix == ".pdf"
    assert written.is_file()
    assert written.parent == _directory(services)


def test_an_export_reports_progress_and_ends_at_one(services: Services) -> None:
    layouts = _layouts(services)
    seen: list[float] = []
    handle = layouts.export(conftest.LAYOUT_NAME)
    handle.on_progress(seen.append)

    _drive(services)

    assert handle.status is JobStatus.SUCCEEDED
    assert seen, "an export that produced a file reported no progress"
    assert seen == sorted(seen), "progress went backwards"
    assert seen[-1] == pytest.approx(1.0)


def test_a_cancelled_export_writes_nothing(services: Services) -> None:
    layouts = _layouts(services)
    handle = layouts.export(conftest.LAYOUT_NAME)

    assert handle.cancel() is True
    _drive(services)

    assert handle.status is JobStatus.CANCELLED
    # Cancellation is not a failure: the job has no error, and reading its
    # result is what raises the cancellation.
    assert handle.error is None
    with pytest.raises(QgisSdkJobCancelledError):
        _ = handle.result
    assert not list(_directory(services).glob(f"{conftest.LAYOUT_NAME}*.pdf"))


def test_two_exports_number_their_files(services: Services) -> None:
    """A second export never replaces the file a page may still be showing."""
    layouts = _layouts(services)

    first = layouts.render(conftest.LAYOUT_NAME)
    second = layouts.render(conftest.LAYOUT_NAME)

    assert first.path != second.path
    assert conftest.Path(first.path).is_file()
    assert conftest.Path(second.path).is_file()


# -- the format policy -----------------------------------------------------------


def test_a_png_of_a_one_page_layout_is_one_image(services: Services) -> None:
    layouts = _layouts(services)

    export = layouts.render(conftest.SINGLE_PAGE_LAYOUT, format="png")

    assert export.format == "png"
    assert export.pages == 1
    assert conftest.Path(export.path).suffix == ".png"
    assert conftest.Path(export.path).is_file()


def test_an_image_of_a_multi_page_layout_is_refused(services: Services) -> None:
    """One image holds one page, so the alternative is a name meaning "the first"."""
    layouts = _layouts(services)

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.render(conftest.LAYOUT_NAME, format="png")

    assert "one page" in str(refused.value)


def test_an_unknown_format_is_refused_by_name(services: Services) -> None:
    layouts = _layouts(services)

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.export(conftest.LAYOUT_NAME, format="tiff")

    assert "tiff" in str(refused.value)


def test_a_missing_layout_is_refused_by_name(services: Services) -> None:
    layouts = _layouts(services)

    with pytest.raises(QgisSdkLayoutNotFoundError) as missing:
        layouts.export("no-such-layout")

    assert missing.value.name == "no-such-layout"


# -- destinations are refs -------------------------------------------------------


def test_a_destination_is_a_ref_not_a_path(services: Services) -> None:
    layouts = _layouts(services)
    path = _directory(services) / "typed-by-hand.pdf"

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.render(conftest.LAYOUT_NAME, destination=str(path))

    assert "FileRef" in str(refused.value)
    assert not path.exists()


def test_an_export_lands_where_the_minted_ref_names(services: Services) -> None:
    layouts = _layouts(services)
    assert services.files is not None
    path = _directory(services) / "granted.pdf"

    export = layouts.render(
        conftest.LAYOUT_NAME,
        destination=services.files.grant_file(
            path, operations=("write",), overwrite=True
        ),
    )

    assert export.path == str(path)
    assert path.is_file()


def test_an_existing_destination_needs_the_overwrite_flag(services: Services) -> None:
    layouts = _layouts(services)
    assert services.files is not None
    path = _directory(services) / "overwritten.pdf"
    ref = services.files.grant_file(path, operations=("write",), overwrite=True)
    layouts.render(conftest.LAYOUT_NAME, destination=ref)

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.render(conftest.LAYOUT_NAME, destination=ref)

    assert "overwrite" in str(refused.value)

    replaced = layouts.render(conftest.LAYOUT_NAME, destination=ref, overwrite=True)

    assert replaced.path == str(path)


# -- the atlas -------------------------------------------------------------------


def test_the_atlas_writes_one_file_per_coverage_feature(services: Services) -> None:
    layouts = _layouts(services)

    run = layouts.render_atlas(conftest.ATLAS_NAME, pattern=conftest.ATLAS_PATTERN)

    assert run.format == "pdf"
    assert tuple(page.feature_id for page in run.pages) == conftest.ATLAS_FEATURE_IDS
    assert tuple(page.index for page in run.pages) == (1, 2, 3)
    for page in run.pages:
        written = conftest.Path(page.path)
        assert written.is_file()
        assert written.name == (
            conftest.ATLAS_PATTERN.format(index=page.index, feature_id=page.feature_id)
            + ".pdf"
        )
        assert written.parent == conftest.Path(run.directory)


def test_the_atlas_reports_progress_and_one_file_per_page(services: Services) -> None:
    layouts = _layouts(services)
    seen: list[float] = []
    handle = layouts.run_atlas(conftest.ATLAS_NAME)
    handle.on_progress(seen.append)

    _drive(services)
    run = handle.result

    total = len(conftest.ATLAS_FEATURE_IDS)
    assert len(run.pages) == total
    # Delivery coalesces progress to the latest fraction per tick (decision-13),
    # so a run that finished inside one worker call reaches a subscriber as its
    # end. The per-page reports are the render's own, and the fake's suite pins
    # them where they can be observed one report at a time.
    assert seen[-1] == pytest.approx(1.0)
    assert seen == sorted(seen)


def test_an_atlas_reports_one_fraction_per_page(services: Services) -> None:
    """The render reports per page; delivery coalesces, so read the work item.

    A subscriber hears the latest fraction once per tick (decision-13), and an
    atlas that finished inside one worker call reaches it as ``1.0``. The
    fractions the render itself reported are what the task bar saw as the bar
    moved, which is what the worker backend was handed.
    """
    layouts = _layouts(services)
    handle = layouts.run_atlas(conftest.ATLAS_NAME, pattern=conftest.ATLAS_PATTERN)
    layouts.jobs.tick()
    assert services.layout_work_items is not None
    items = services.layout_work_items()
    assert items, "the atlas job never reached the worker backend"
    assert items[-1].title == f"Run atlas {conftest.ATLAS_NAME!r}"

    reported: list[float] = []
    assert items[-1].progress is not None
    items[-1].progress.observe(reported.append)

    _drive(services)

    total = len(conftest.ATLAS_FEATURE_IDS)
    assert handle.status is JobStatus.SUCCEEDED
    assert reported == pytest.approx([step / total for step in range(1, total + 1)])


def test_an_atlas_pattern_may_not_name_an_unknown_field(services: Services) -> None:
    layouts = _layouts(services)

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.render_atlas(conftest.ATLAS_NAME, pattern="{page}.{feature_id}")

    assert "page" in str(refused.value)


def test_a_layout_without_an_atlas_cannot_run_one(services: Services) -> None:
    layouts = _layouts(services)

    with pytest.raises(QgisSdkExportRefusedError) as refused:
        layouts.render_atlas(conftest.LAYOUT_NAME)

    assert "no atlas" in str(refused.value)
