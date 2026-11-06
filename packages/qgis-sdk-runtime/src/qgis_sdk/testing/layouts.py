"""A ``Layouts`` backend over layouts a test declares, with no QGIS behind it.

The fake exists for the same reason :class:`~qgis_sdk.testing.FakeRasters` does:
so a workflow exports a print layout in a pure test, and so the contract suite
can hold this backend and the native one to identical expectations. It is not a
layout engine, and three limits are deliberate rather than accidental.

*Rendering writes a marker file, not a page.* A fake that drew a page would need
a renderer, fonts and a QGIS to agree with, which is a second implementation and
not a test double. Each format gets its own short, recognisable header - the PDF
magic, the PNG signature, an ``<svg>`` root - so a test can prove *which* format
was written, and the rest of the file says whose page it would have been.

*The atlas iterates the coverage ids a test declares.* Native walks the real
coverage layer; the fake walks the ids it was given, in order, and reports the
same ``index``/``feature_id`` pairs, so one contract test asserts both.

*Every export goes through the shared policy.* Format, destination, overwrite,
staging, commit and cleanup are :mod:`qgis_sdk.exports` - the same code path the
native adapter runs - so a refusal here is the refusal a caller hears there.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.layouts import LayoutService
from qgis_sdk.models import (
    LAYOUT_SUFFIXES,
    SINGLE_PAGE_FORMATS,
    AtlasExport,
    AtlasInfo,
    AtlasRequest,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    QgisSdkExportRefusedError,
    QgisSdkLayoutNotFoundError,
)
from qgis_sdk.services.contracts import Cancellation, Progress
from qgis_sdk.services.layouts import (
    atlas_pages,
    exported,
    free_layout_name,
    page_path,
    stop_if_cancelled,
)

__all__ = ["FakeLayouts"]

#: What each format starts with, so a test can tell the file it got. The bytes
#: after the header name the layout and the page, which is enough for a reader
#: to recognise a fake and enough for a test to tell two exports apart.
_MARKERS = {
    "pdf": b"%PDF-1.4\n",
    "png": b"\x89PNG\r\n\x1a\n",
    "svg": b'<?xml version="1.0" encoding="utf-8"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>\n',
}


class FakeLayouts(LayoutService):
    """``Layouts`` over layouts declared in a test, exporting marker files.

    A test declares a layout (``declare_layout``) and, for an atlas, the
    coverage feature ids it iterates (``declare_atlas``); a template it wants to
    load is a file it writes itself, because loading one is the native adapter's
    real work and the fake only has to answer the same description.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        workers: Any,
        files: Any = None,
        working_directory: Path,
    ) -> None:
        self._scope = scope
        self._directory = Path(working_directory)
        self._layouts: dict[str, LayoutInfo] = {}
        self._coverage: dict[str, tuple[int, ...]] = {}
        super().__init__(
            _FakeBackend(self),
            scope=scope,
            workers=workers,
            files=files,
            working_directory=self._directory,
        )
        scope.on_close(self._release)

    # -- what a test declares ---------------------------------------------------

    def declare_layout(self, name: str, *, pages: int = 1) -> LayoutInfo:
        """Declare a layout with ``pages`` pages and no atlas."""
        info = LayoutInfo(id=name, name=name, page_count=pages)
        self._layouts[name] = info
        return info

    def declare_atlas(
        self,
        name: str,
        *,
        coverage_layer: str,
        feature_ids: Sequence[int],
        pages: int = 1,
    ) -> LayoutInfo:
        """Declare a layout whose atlas covers ``feature_ids`` of ``coverage_layer``."""
        if not feature_ids:
            raise ValueError("an atlas covers at least one feature")
        info = LayoutInfo(
            id=name,
            name=name,
            page_count=pages,
            atlas=AtlasInfo(
                enabled=True,
                coverage_layer=coverage_layer,
                filename_expression="'sheet-' || @atlas_featureid",
            ),
        )
        self._layouts[name] = info
        self._coverage[name] = tuple(int(feature_id) for feature_id in feature_ids)
        return info

    # -- what the renderer reads ------------------------------------------------

    def _declared(self) -> tuple[LayoutInfo, ...]:
        """Every declared layout, in declaration order."""
        return tuple(self._layouts.values())

    def _info(self, name: str) -> LayoutInfo:
        """One declared layout, or the not-found error both backends raise."""
        info = self._layouts.get(name)
        if info is None:
            raise QgisSdkLayoutNotFoundError(name)
        return info

    def _coverage_ids(self, name: str) -> tuple[int, ...] | None:
        """The feature ids the named layout's atlas covers, if it has one."""
        return self._coverage.get(name)

    def _release(self) -> None:
        """Forget every declared layout; the files already written stay."""
        self._layouts.clear()
        self._coverage.clear()


class _FakeBackend:
    """The renderer half: marker files through the shared export policy."""

    def __init__(self, layouts: FakeLayouts) -> None:
        self._layouts = layouts

    def list(self) -> tuple[LayoutInfo, ...]:
        return self._layouts._declared()

    def load_template(self, template: Path) -> LayoutInfo:
        """Answer a layout named after the template, as QGIS would."""
        if not template.is_file():
            raise QgisSdkExportRefusedError(
                str(template), ["the template file does not exist"]
            )
        info = self._layouts.declare_layout(
            free_layout_name(
                (existing.name for existing in self._layouts._declared()),
                template.stem,
            )
        )
        return info

    def render(
        self,
        request: LayoutRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> LayoutExport:
        _check_format(request.format, request.destination)
        info = self._layouts._info(request.layout)
        _check_page_count(info, request)
        stop_if_cancelled(cancellation)
        plan = export_policy.plan_export(
            Path(request.destination),
            overwrite=request.overwrite,
            drivers=LAYOUT_SUFFIXES,
        )
        pages = info.page_count if request.format == "pdf" else 1
        body = self._bytes(request, pages=pages)
        export_policy.run_export(plan, lambda partial: partial.write_bytes(body))
        progress.report(1.0)
        return exported(request, plan.destination, pages=pages)

    def render_atlas(
        self,
        request: AtlasRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> AtlasExport:
        _check_format(request.format, request.directory)
        self._layouts._info(request.layout)
        feature_ids = self._layouts._coverage_ids(request.layout)
        if feature_ids is None:
            raise QgisSdkExportRefusedError(
                request.layout,
                [
                    (
                        "the layout has no atlas; an atlas needs a coverage layer, "
                        "which no backend can add for a caller"
                    )
                ],
            )
        written: list[tuple[int, int | None, Path]] = []
        total = len(feature_ids)
        for index, feature_id in enumerate(feature_ids):
            stop_if_cancelled(cancellation)
            path = page_path(request, index=index + 1, feature_id=feature_id)
            plan = export_policy.plan_export(
                path, overwrite=request.overwrite, drivers=LAYOUT_SUFFIXES
            )
            body = self._bytes(request, pages=1, page=index + 1)
            export_policy.run_export(
                plan, lambda partial, payload=body: partial.write_bytes(payload)
            )
            written.append((index + 1, feature_id, plan.destination))
            progress.report((index + 1) / total)
        return atlas_pages(request, written)

    # -- helpers ----------------------------------------------------------------

    def _bytes(
        self, request: LayoutRequest | AtlasRequest, *, pages: int, page: int = 1
    ):
        """The marker bytes one file holds; ``pages`` names how many it claims."""
        header = _MARKERS[request.format]
        line = f"{request.layout} page {page} of {pages}\n".encode()
        return header + line


def _check_page_count(info: LayoutInfo, request: LayoutRequest) -> None:
    """Refuse an image export of a multi-page layout, naming why.

    A single image holds a single page, so the alternative is a file name that
    quietly means "the first page"; the SDK refuses instead (documented in
    :mod:`qgis_sdk.services.layouts`).
    """
    if request.format in SINGLE_PAGE_FORMATS and info.page_count > 1:
        raise QgisSdkExportRefusedError(
            request.destination,
            [
                (
                    f"a {request.format} file holds one page and the layout has "
                    f"{info.page_count}; export it as pdf or run its atlas"
                )
            ],
        )


def _check_format(format: str, destination: str) -> None:
    """Refuse a format no file can carry, for a backend called without the service."""
    if format not in _MARKERS:
        raise QgisSdkExportRefusedError(
            destination,
            [
                (
                    f"unsupported format {format!r}; a layout exports to "
                    f"{', '.join(sorted(_MARKERS))}"
                )
            ],
        )
