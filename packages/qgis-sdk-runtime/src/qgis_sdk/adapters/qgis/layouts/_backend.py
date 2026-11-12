"""The renderer half: ``QgsLayoutManager`` reads and ``QgsLayoutExporter``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import qgis_sdk.exports as export_policy
from qgis_sdk.models import (
    LAYOUT_SUFFIXES,
    AtlasExport,
    AtlasRequest,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    QgisSdkExportFailedError,
    QgisSdkLayoutNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.services.contracts import Cancellation, Progress
from qgis_sdk.services.layouts import free_layout_name, stop_if_cancelled

from ._helpers import describe, settings, template_document
from ._render import AtlasFacts, RenderFacts, check_pages, enabled_atlas, render_export

__all__ = ["NativeLayoutsBackend"]


class NativeLayoutsBackend:
    """The renderer half: ``QgsLayoutManager`` reads and ``QgsLayoutExporter``."""

    def __init__(self, core: Any) -> None:
        self._core = core

    # -- reads and project edits ------------------------------------------------

    def list(self) -> tuple[LayoutInfo, ...]:
        return tuple(describe(layout) for layout in self._manager().printLayouts())

    def load_template(self, template: Path) -> LayoutInfo:
        """Load a ``.qpt`` into a new layout named after the file.

        QGIS's own recipe for a template: read the file, parse it as a document
        and load its items into a fresh ``QgsPrintLayout``. The layout takes the
        template file's name because a ``.qpt`` carries no name of its own -
        which is also the name the fake adds, so both backends answer the same.
        """
        core = self._core
        document = template_document(template)
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
        return describe(layout)

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
        check_pages(request, pages)
        stop_if_cancelled(cancellation)
        plan = export_policy.plan_export(
            Path(request.destination),
            overwrite=request.overwrite,
            drivers=LAYOUT_SUFFIXES,
        )
        facts = RenderFacts(
            backend=self,
            exporter=self._core.QgsLayoutExporter(layout),
            request=request,
            settings=settings(self._core, request),
            plan=plan,
            pages=pages,
            progress=progress,
        )
        return render_export(facts)

    def render_atlas(
        self,
        request: AtlasRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> AtlasExport:
        core = self._core
        layout = self._layout(request.layout)
        atlas = enabled_atlas(layout, request)
        facts = AtlasFacts(
            core=core,
            layout=layout,
            atlas=atlas,
            exporter=core.QgsLayoutExporter(layout),
            settings=settings(core, request),
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
