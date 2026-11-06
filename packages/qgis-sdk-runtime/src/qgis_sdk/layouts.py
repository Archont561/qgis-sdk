"""The layouts service implementation: refs, destinations and jobs (TASK-89).

The Protocol an author programs against is
:class:`qgis_sdk.services.layouts.Layouts`, and a bare PyQGIS-free contract
cannot submit a job: a job needs :class:`~qgis_sdk.jobs.JobService`, which is a
higher layer than the pure service protocols. This module is that higher layer -
the same split :mod:`qgis_sdk.files` has from ``services.files`` - and it holds
the one implementation of the policy every backend shares: which thread resolves
a ref, where a destination-less export lands, what a job is titled, and that a
blocking render reports nowhere. The fake and the native adapter both subclass
it, so the contract suite holds one implementation of the policy and two of the
drawing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from qgis_sdk.core import WorkerContext
from qgis_sdk.jobs import JobHandle, JobService, job
from qgis_sdk.models import (
    LAYOUT_FORMATS,
    LAYOUT_SUFFIXES,
    SINGLE_PAGE_FORMATS,
    AtlasExport,
    AtlasRequest,
    FileRef,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    LayoutSettings,
    QgisSdkExportRefusedError,
    QgisSdkLayoutNotFoundError,
)
from qgis_sdk.services.layouts import (
    ATLAS_JOB_ID,
    EXPORT_JOB_ID,
    LayoutBackend,
    NullCancellation,
    NullProgress,
    _check_pattern,
    _slug,
)

__all__ = ["ATLAS_JOB_ID", "EXPORT_JOB_ID", "LayoutService"]


class LayoutService:
    """The backend-agnostic half of ``Layouts``: refs, paths and jobs.

    An adapter supplies a :class:`LayoutBackend` and this class supplies the
    policy every backend shares: which thread resolves a ref, which directory a
    destination-less export lands in, what a job is titled, and that a blocking
    render reports nowhere. The fake and the native adapter both subclass it, so
    the contract suite holds one implementation of the policy and two of the
    drawing.
    """

    def __init__(
        self,
        backend: LayoutBackend,
        *,
        scope: Any,
        workers: Any,
        files: Any = None,
        working_directory: Path,
    ) -> None:
        self._backend = backend
        self._files = files
        self._working_directory = Path(working_directory)
        # One job service per layouts service, on the plugin's own scope: the
        # host pumps it beside ``ctx.jobs``, and a plugin that declared no jobs
        # of its own still exports with a bar and a cancel button.
        self._jobs = JobService(scope, workers=workers)

    @property
    def jobs(self) -> Any:
        """The job service the two job forms submit through, for the host to pump."""
        return self._jobs

    # -- reads and project edits ------------------------------------------------

    def list(self) -> tuple[LayoutInfo, ...]:
        """Every print layout in the project, in the manager's order."""
        return self._backend.list()

    def load_template(self, template: FileRef) -> LayoutInfo:
        """Load a template file into the project and describe the new layout."""
        return self._backend.load_template(self._path(template, "read"))

    # -- exports ----------------------------------------------------------------

    def export(
        self,
        layout: str,
        *,
        format: str = "pdf",
        destination: FileRef | None = None,
        settings: LayoutSettings | None = None,
        overwrite: bool = False,
    ) -> JobHandle:
        """Export a layout as a job; the outcome is a ``LayoutExport``."""
        request = self._export_request(
            layout,
            format=format,
            destination=destination,
            settings=settings,
            overwrite=overwrite,
        )
        return self._jobs.bind(_export_body(self._backend, layout)).delay(
            request=request
        )

    def render(
        self,
        layout: str,
        *,
        format: str = "pdf",
        destination: FileRef | None = None,
        settings: LayoutSettings | None = None,
        overwrite: bool = False,
    ) -> LayoutExport:
        """Export a layout here and now: no job, no progress bar."""
        return self._backend.render(
            self._export_request(
                layout,
                format=format,
                destination=destination,
                settings=settings,
                overwrite=overwrite,
            ),
            progress=NullProgress(),
            cancellation=NullCancellation(),
        )

    def run_atlas(
        self,
        layout: str,
        *,
        format: str = "pdf",
        directory: FileRef | None = None,
        pattern: str | None = None,
        settings: LayoutSettings | None = None,
        overwrite: bool = False,
    ) -> JobHandle:
        """Run a layout's atlas as a job; the outcome is an ``AtlasExport``."""
        request = self._atlas_request(
            layout,
            format=format,
            directory=directory,
            pattern=pattern,
            settings=settings,
            overwrite=overwrite,
        )
        return self._jobs.bind(_atlas_body(self._backend, layout)).delay(
            request=request
        )

    def render_atlas(
        self,
        layout: str,
        *,
        format: str = "pdf",
        directory: FileRef | None = None,
        pattern: str | None = None,
        settings: LayoutSettings | None = None,
        overwrite: bool = False,
    ) -> AtlasExport:
        """Run a layout's atlas here and now: no job, no progress bar."""
        return self._backend.render_atlas(
            self._atlas_request(
                layout,
                format=format,
                directory=directory,
                pattern=pattern,
                settings=settings,
                overwrite=overwrite,
            ),
            progress=NullProgress(),
            cancellation=NullCancellation(),
        )

    # -- policy -----------------------------------------------------------------

    def _export_request(
        self,
        layout: str,
        *,
        format: str,
        destination: FileRef | None,
        settings: LayoutSettings | None,
        overwrite: bool,
    ) -> LayoutRequest:
        """Build the plain request a render needs, refusing here, not on a worker."""
        self._check_format(format)
        info = self._require(layout)
        if format in SINGLE_PAGE_FORMATS and info.page_count > 1:
            raise QgisSdkExportRefusedError(
                layout,
                [
                    (
                        f"a {format} file holds one page and the layout has "
                        f"{info.page_count}; export it as pdf or run its atlas"
                    )
                ],
            )
        if destination is None:
            path = self._free_path(f"{_slug(layout)}{LAYOUT_FORMATS[format]}")
            overwrite = False
        else:
            path = self._path(destination, "write")
        return LayoutRequest(
            layout=layout,
            format=format,
            destination=str(path),
            settings=settings or LayoutSettings(),
            overwrite=overwrite,
        )

    def _atlas_request(
        self,
        layout: str,
        *,
        format: str,
        directory: FileRef | None,
        pattern: str | None,
        settings: LayoutSettings | None,
        overwrite: bool,
    ) -> AtlasRequest:
        """Build the plain atlas request, with the pattern already checked."""
        self._check_format(format)
        if directory is None:
            target = self._working_directory / _slug(layout)
        else:
            target = self._path(directory, "write")
        target.mkdir(parents=True, exist_ok=True)
        return AtlasRequest(
            layout=layout,
            format=format,
            directory=str(target),
            pattern=_check_pattern(pattern or "page-{index:03d}"),
            settings=settings or LayoutSettings(),
            overwrite=overwrite,
        )

    def _require(self, layout: str) -> LayoutInfo:
        """The named layout, refused here rather than on a worker.

        A name the project does not hold is a caller's mistake, and a job that
        fails minutes later is a worse way to learn it than an exception from
        the call that submitted it.
        """
        for info in self._backend.list():
            if info.name == layout:
                return info
        raise QgisSdkLayoutNotFoundError(layout)

    def _check_format(self, format: str) -> None:
        """Refuse a format this SDK does not write, naming the ones it does."""
        if format in LAYOUT_FORMATS:
            return
        reasons = [
            (
                "unsupported format "
                f"{format!r}; a layout exports to {', '.join(sorted(LAYOUT_FORMATS))}"
            )
        ]
        if format in LAYOUT_SUFFIXES:
            reasons = [
                (
                    f"{format!r} is a suffix, not a format; name "
                    f"{LAYOUT_SUFFIXES[format]!r} and let the export add the suffix"
                )
            ]
        raise QgisSdkExportRefusedError(format, reasons)

    def _free_path(self, name: str) -> Path:
        """A path in the host's output directory that no earlier export holds.

        A second export of the same layout does not silently replace the first
        one the page may still be showing: it gets ``report-2.pdf``.
        """
        self._working_directory.mkdir(parents=True, exist_ok=True)
        candidate = self._working_directory / name
        number = 2
        stem, suffix = candidate.stem, candidate.suffix
        while candidate.exists():
            candidate = self._working_directory / f"{stem}-{number}{suffix}"
            number += 1
        return candidate

    def _path(self, ref: FileRef, operation: str) -> Path:
        """Resolve a minted ref, refusing a bare path the caller typed itself."""
        if not isinstance(ref, FileRef):
            raise QgisSdkExportRefusedError(
                str(ref),
                [
                    (
                        "a destination is a FileRef the host minted, not a path "
                        "(decision-20); ask ctx.files for one"
                    )
                ],
            )
        return Path(self._files.resolve(ref, operation=operation))


def _export_body(backend: LayoutBackend, layout: str) -> Callable[..., Any]:
    """The ``@job`` body of one layout export, as a declaration.

    Built per call because the body is the only place the backend may be
    reached from a worker: the closure holds an adapter, never a live layout,
    and the request that crosses to the worker is plain values.
    """

    @job(id=EXPORT_JOB_ID, title=f"Export layout {layout!r}")
    def body(ctx: WorkerContext, request: LayoutRequest) -> LayoutExport:
        return backend.render(
            request, progress=ctx.progress, cancellation=ctx.cancellation
        )

    return body


def _atlas_body(backend: LayoutBackend, layout: str) -> Callable[..., Any]:
    """The ``@job`` body of one atlas run, as a declaration."""

    @job(id=ATLAS_JOB_ID, title=f"Run atlas {layout!r}")
    def body(ctx: WorkerContext, request: AtlasRequest) -> AtlasExport:
        return backend.render_atlas(
            request, progress=ctx.progress, cancellation=ctx.cancellation
        )

    return body
