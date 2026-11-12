"""``Layouts`` over PyQGIS: the layout manager and ``QgsLayoutExporter``.

The curated contract is :class:`~qgis_sdk.services.layouts.Layouts`; this module
is the half that has QGIS in it, and four choices are worth stating.

*A layout is found by name in the project's layout manager.* That is where the
print designer puts one and where a template lands, so nothing here keeps a
second registry that could disagree with what the user sees.

*Rendering is a worker's job, and a task in the task manager.* The service
submits a ``@job`` whose body is :meth:`_NativeLayoutsBackend.render`; the
desktop worker backend runs it as one ``QgsTask``, so the export appears in the
QGIS task bar named after the layout, its bar follows ``ctx.progress`` and its
cancel button asks the job to stop (decision-65). The body therefore holds a
name and plain settings, resolves the layout inside the worker and never carries
a live ``QgsLayout`` from the driving thread - the same recipe QGIS Server uses
when it renders a print layout per request.

*The exporter's result enum decides what a caller hears.* ``Success`` returns
the file, ``Canceled`` raises ``QgisSdkJobCancelledError`` so the job settles as
cancelled, and every other code raises ``QgisSdkExportFailedError`` carrying
``errorMessage()``. Nothing is inferred from the absence of an exception, and
the file is written through :mod:`qgis_sdk.exports`, so a failed render leaves
the previous destination untouched.

*An atlas is iterated here, not by the exporter's static overloads.* Those name
the files themselves from the layout's own file-name expression, which would put
a project setting between the caller's pattern and the file on disk. Seeking the
atlas page by page and exporting each one gives the caller's pattern, the page's
own feature id - the one ``prepareForFeature`` put in the layout's report
context - a progress report per page and a cancellation check between them.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.layouts import LayoutService, LayoutWiring
from qgis_sdk.models import (
    LAYOUT_SUFFIXES,
    SINGLE_PAGE_FORMATS,
    AtlasExport,
    AtlasInfo,
    AtlasRequest,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    QgisSdkExportFailedError,
    QgisSdkExportRefusedError,
    QgisSdkJobCancelledError,
    QgisSdkLayoutNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.services.contracts import Cancellation, Progress
from qgis_sdk.services.layouts import (
    atlas_pages,
    exported,
    free_layout_name,
    page_path,
    stop_if_cancelled,
)


@dataclass(frozen=True, slots=True)
class _RenderFacts:
    """Everything one single-layout export needs, as one record."""

    backend: Any
    exporter: Any
    request: LayoutRequest
    settings: Any
    plan: Any
    pages: int
    progress: Progress


def _render_export(facts: _RenderFacts) -> LayoutExport:
    """Write the planned file, report completion, and describe the export."""
    export_policy.run_export(
        facts.plan,
        lambda partial: _write(
            facts.backend._core,
            facts.exporter,
            facts.request,
            partial,
            facts.settings,
        ),
    )
    facts.progress.report(1.0)
    return exported(facts.request, facts.plan.destination, pages=facts.pages)


def _check_pages(request: LayoutRequest, pages: int) -> None:
    """A layout needs a page, and a single-page format needs exactly one."""
    if pages < 1:
        raise QgisSdkExportRefusedError(
            request.destination, ["the layout has no page to export"]
        )
    if request.format in SINGLE_PAGE_FORMATS and pages > 1:
        raise QgisSdkExportRefusedError(
            request.destination,
            [
                (
                    f"a {request.format} file holds one page and the layout has "
                    f"{pages}; export it as pdf or run its atlas"
                )
            ],
        )


def _enabled_atlas(layout: Any, request: AtlasRequest) -> Any:
    """The layout's atlas, refused by name when the designer never enabled one."""
    atlas = layout.atlas()
    if atlas is None or not atlas.enabled():
        raise QgisSdkExportRefusedError(
            request.directory,
            [
                (
                    "the layout has no atlas; enable one over a coverage layer in "
                    "the print designer, because no backend can add one for a caller"
                )
            ],
        )
    return atlas


@dataclass(frozen=True, slots=True)
class _AtlasFacts:
    """The atlas, its exporter and the caller's request, held as one record."""

    core: Any
    layout: Any
    atlas: Any
    exporter: Any
    settings: Any
    request: AtlasRequest
    progress: Progress
    cancellation: Cancellation

    def render(self) -> AtlasExport:
        """Iterate the pages once, then hand the written files to the caller."""
        if not self.atlas.beginRender():  # pragma: no cover - empty coverage layer
            raise QgisSdkExportRefusedError(
                self.request.directory,
                ["the atlas covered no feature; its coverage layer selected nothing"],
            )
        written: list[tuple[int, int | None, Path]] = []
        try:
            total = self.atlas.count()
            if total < 1:  # pragma: no cover - beginRender refused an empty atlas
                raise QgisSdkExportRefusedError(
                    self.request.directory, ["the atlas has no page to write"]
                )
            for index in range(total):
                self._write_page(index, total, written)
        finally:
            self.atlas.endRender()
        return atlas_pages(self.request, written)

    def _write_page(self, index: int, total: int, written: list) -> None:
        """Seek to one page, export it under the caller's pattern, report progress."""
        stop_if_cancelled(self.cancellation)
        if not self.atlas.seekTo(index):
            raise QgisSdkExportFailedError(
                self.request.directory,
                f"the atlas could not seek to page {index + 1} of {total}",
            )
        # ``prepareForFeature`` put the page's coverage feature in the
        # layout's report context, which is where its id is readable.
        feature = self.layout.reportContext().feature()
        feature_id = int(feature.id()) if feature.isValid() else None
        path = page_path(self.request, index=index + 1, feature_id=feature_id)
        plan = export_policy.plan_export(
            path, overwrite=self.request.overwrite, drivers=LAYOUT_SUFFIXES
        )
        export_policy.run_export(
            plan,
            lambda partial: _write(
                self.core, self.exporter, self.request, partial, self.settings
            ),
        )
        written.append((index + 1, feature_id, plan.destination))
        self.progress.report((index + 1) / total)


def _template_document_phase1(content, document, path):
    if not document.setContent(content):
        raise QgisSdkExportRefusedError(
            path,
            [
                (
                    "the file is not a print-layout template; a template is a .qpt "
                    "written by the print designer"
                )
            ],
        )
    return document


__all__ = ["NativeLayouts"]


def _core() -> Any:
    """Import the QGIS core module, or refuse the capability by name."""
    try:
        from qgis import core
    except ImportError as error:  # pragma: no cover - depends on the host build
        raise QgisSdkUnsupportedCapabilityError(
            "NativeLayouts",
            "print layouts need PyQGIS; this host imported without qgis.core",
        ) from error
    return core


class NativeLayouts(LayoutService):
    """``Layouts`` over the project's layout manager and QGIS's exporter.

    ``working_directory`` is where an export lands when the caller gave no
    destination; it defaults to a per-session temporary directory, so an export
    a caller never named is still a file the host owns (decision-20).
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        workers: Any,
        files: Any = None,
        working_directory: Path | None = None,
    ) -> None:
        core = _core()
        self._scope = scope
        self._working_directory = Path(
            working_directory
            if working_directory is not None
            else tempfile.mkdtemp(prefix="qgis-sdk-layouts-")
        )
        super().__init__(
            LayoutWiring(
                backend=_NativeLayoutsBackend(core),
                scope=scope,
                working_directory=self._working_directory,
                workers=workers,
                files=files,
            )
        )
        scope.on_close(self._release)

    @property
    def working_directory(self) -> Path:
        """Where a destination-less export is written."""
        return self._working_directory

    def _release(self) -> None:
        """Nothing to forget: the layouts belong to the project, not to this adapter."""


class _NativeLayoutsBackend:
    """The renderer half: ``QgsLayoutManager`` reads and ``QgsLayoutExporter``."""

    def __init__(self, core: Any) -> None:
        self._core = core

    # -- reads and project edits ------------------------------------------------

    def list(self) -> tuple[LayoutInfo, ...]:
        return tuple(_describe(layout) for layout in self._manager().printLayouts())

    def load_template(self, template: Path) -> LayoutInfo:
        """Load a ``.qpt`` into a new layout named after the file.

        QGIS's own recipe for a template: read the file, parse it as a document
        and load its items into a fresh ``QgsPrintLayout``. The layout takes the
        template file's name because a ``.qpt`` carries no name of its own -
        which is also the name the fake adds, so both backends answer the same.
        """
        core = self._core
        document = _template_document(template)
        layout = core.QgsPrintLayout(core.QgsProject.instance())
        layout.loadFromTemplate(document, core.QgsReadWriteContext(), False)
        manager = self._manager()
        layout.setName(
            free_layout_name(
                (existing.name() for existing in manager.printLayouts()),
                template.stem,
            )
        )
        if not manager.addLayout(layout):
            raise QgisSdkExportFailedError(
                str(template), "QGIS refused to add the loaded layout to the project"
            )
        return _describe(layout)

    # -- rendering --------------------------------------------------------------

    def render(
        self,
        request: LayoutRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> LayoutExport:
        layout = self._layout(request.layout)
        pages = layout.pageCollection().pageCount()
        _check_pages(request, pages)
        stop_if_cancelled(cancellation)
        plan = export_policy.plan_export(
            Path(request.destination),
            overwrite=request.overwrite,
            drivers=LAYOUT_SUFFIXES,
        )
        facts = _RenderFacts(
            backend=self,
            exporter=self._core.QgsLayoutExporter(layout),
            request=request,
            settings=_settings(self._core, request),
            plan=plan,
            pages=pages,
            progress=progress,
        )
        return _render_export(facts)

    def render_atlas(
        self,
        request: AtlasRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> AtlasExport:
        core = self._core
        layout = self._layout(request.layout)
        atlas = _enabled_atlas(layout, request)
        facts = _AtlasFacts(
            core=core,
            layout=layout,
            atlas=atlas,
            exporter=core.QgsLayoutExporter(layout),
            settings=_settings(core, request),
            request=request,
            progress=progress,
            cancellation=cancellation,
        )
        return facts.render()

    # -- helpers ----------------------------------------------------------------

    def _manager(self) -> Any:
        """The project's layout manager, the one list a user's layouts live in."""
        project = self._core.QgsProject.instance()
        if project is None:  # pragma: no cover - a QgsApplication always has one
            raise QgisSdkUnsupportedCapabilityError(
                "NativeLayouts", "no QGIS project is open, so there are no layouts"
            )
        return project.layoutManager()

    def _layout(self, name: str) -> Any:
        layout = self._manager().layoutByName(name)
        if layout is None:
            raise QgisSdkLayoutNotFoundError(name)
        return layout


def _template_document(template: Path) -> Any:
    """Parse a ``.qpt`` file, refusing anything QGIS could not read as one.

    ``QFile`` and ``QDomDocument`` are Qt classes, not ``qgis.core`` ones: the
    template is read as bytes and parsed by Qt's own XML reader, which is what
    ``QgsLayout.loadFromTemplate`` takes. PyQt5 spells the open mode on
    ``QIODevice`` and PyQt6 nests the same name in an enum, so both are read.
    """
    from qgis.PyQt.QtCore import QFile, QIODevice
    from qgis.PyQt.QtXml import QDomDocument

    path = str(template)
    file = QFile(path)
    mode = getattr(QIODevice, "OpenModeFlag", QIODevice)
    if not file.open(mode.ReadOnly):
        raise QgisSdkExportRefusedError(path, ["the template file could not be read"])
    try:
        content = file.readAll()
    finally:
        file.close()
    document = QDomDocument()
    return _template_document_phase1(content, document, path)


def _describe(layout: Any) -> LayoutInfo:
    """Translate one ``QgsPrintLayout`` into the plain description a caller gets."""
    atlas = layout.atlas()
    info = None
    if atlas is not None and atlas.enabled():
        coverage = atlas.coverageLayer()
        info = AtlasInfo(
            enabled=True,
            coverage_layer=None if coverage is None else coverage.name(),
            filename_expression=atlas.filenameExpression() or None,
        )
    return LayoutInfo(
        id=layout.name(),
        name=layout.name(),
        page_count=max(1, layout.pageCollection().pageCount()),
        atlas=info,
    )


def _settings(core: Any, request: LayoutRequest | AtlasRequest) -> Any:
    """Build the exporter's settings object for one format.

    The three settings classes carry different fields, so each is built by its
    own name and filled with what it actually has: the PDF one is the only one
    that can rasterise the whole page, the image one is the only one that writes
    a world file, and the SVG one decides vector fidelity through
    ``forceVectorOutput`` - which is why ``rasterize`` means "let the exporter
    fall back to a raster item" there.
    """
    settings = request.settings
    if request.format == "pdf":
        built = core.QgsLayoutExporter.PdfExportSettings()
        built.rasterizeWholeImage = settings.rasterize
        built.forceVectorOutput = not settings.rasterize
        built.appendGeoreference = settings.georeference
        built.exportMetadata = False
    elif request.format == "png":
        built = core.QgsLayoutExporter.ImageExportSettings()
        built.generateWorldFile = settings.georeference
        built.exportMetadata = False
    else:
        built = core.QgsLayoutExporter.SvgExportSettings()
        built.forceVectorOutput = not settings.rasterize
        built.exportMetadata = False
    built.dpi = settings.dpi
    return built


def _write(
    core: Any,
    exporter: Any,
    request: LayoutRequest | AtlasRequest,
    destination: Path,
    settings: Any,
) -> None:
    """Write one file with ``exporter`` and translate its result into an error."""
    method: Callable[[str, Any], Any] = {
        "pdf": exporter.exportToPdf,
        "png": exporter.exportToImage,
        "svg": exporter.exportToSvg,
    }[request.format]
    result = method(str(destination), settings)
    if result == core.QgsLayoutExporter.Success:
        return
    if result == core.QgsLayoutExporter.Canceled:
        raise QgisSdkJobCancelledError(0)
    detail = exporter.errorMessage() or f"the exporter answered result code {result}"
    error_file = exporter.errorFile()
    if error_file:
        detail = f"{detail} (in {error_file})"
    raise QgisSdkExportFailedError(str(destination), detail)
