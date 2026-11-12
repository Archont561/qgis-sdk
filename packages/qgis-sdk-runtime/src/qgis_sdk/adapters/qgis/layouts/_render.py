"""Single-layout and atlas rendering: the facts, the export, the iteration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import qgis_sdk.exports as export_policy
from qgis_sdk.models import (
    LAYOUT_SUFFIXES,
    SINGLE_PAGE_FORMATS,
    AtlasExport,
    AtlasRequest,
    LayoutExport,
    LayoutRequest,
    QgisSdkExportFailedError,
    QgisSdkExportRefusedError,
)
from qgis_sdk.services.contracts import Cancellation, Progress
from qgis_sdk.services.layouts import (
    atlas_pages,
    exported,
    page_path,
    stop_if_cancelled,
)

from ._helpers import write

__all__ = ["AtlasFacts", "RenderFacts", "check_pages", "enabled_atlas", "render_export"]


@dataclass(frozen=True, slots=True)
class RenderFacts:
    """Everything one single-layout export needs, as one record."""

    backend: Any
    exporter: Any
    request: LayoutRequest
    settings: Any
    plan: Any
    pages: int
    progress: Progress


def render_export(facts: RenderFacts) -> LayoutExport:
    """Write the planned file, report completion, and describe the export."""
    export_policy.run_export(
        facts.plan,
        lambda partial: write(
            facts.backend._core,
            facts.exporter,
            facts.request,
            partial,
            facts.settings,
        ),
    )
    facts.progress.report(1.0)
    return exported(facts.request, facts.plan.destination, pages=facts.pages)


def check_pages(request: LayoutRequest, pages: int) -> None:
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


def enabled_atlas(layout: Any, request: AtlasRequest) -> Any:
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
class AtlasFacts:
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
            lambda partial: write(
                self.core, self.exporter, self.request, partial, self.settings
            ),
        )
        written.append((index + 1, feature_id, plan.destination))
        self.progress.report((index + 1) / total)
