"""Print layouts: list them, load a template, export one, run an atlas.

TASK-89 and decision-54 point 3. A print layout is a page the user composed, and
what a plugin wants from one is a file: list what the project holds, load a
template into it, export a layout to PDF, PNG or SVG, and write one file per
coverage feature of an atlas. Five choices are deliberate.

*Listing and loading are plain calls; exporting is a job.* Listing reads the
project's layout manager and loading a template edits it, both in microseconds,
on the thread that owns the project - the same thread a plugin action already
runs on. An export is minutes of rendering on a real layout, so
:meth:`Layouts.export` and :meth:`Layouts.run_atlas` submit a ``@job`` and answer
a handle: the body runs on a worker (decision-65), the native backend shows it in
the QGIS task manager as one task, its bar follows ``ctx.progress`` and its
cancel button asks the render to stop. :meth:`Layouts.render` and
:meth:`Layouts.render_atlas` are the same work without a job, for the caller
that has to answer inside one request - the bridge, a script, a test.

*A destination is a ref, never a path.* A caller either passes no destination, in
which case the host writes into its own output directory and returns a file the
host still owns, or passes a :class:`~qgis_sdk.models.FileRef` the host minted
(decision-20). A bare string is refused: a path a caller could have typed is not
authority, and the page has none to give.

*The service, not the adapter, owns the job.* ``export`` builds the plain
:class:`~qgis_sdk.models.LayoutRequest` a body needs on the driving thread -
resolving the ref there, where the files service may be read - and hands the
backend a request with no live layout, no ref and no scope in it. That keeps the
fake and the native adapter answering the same values and keeps the render free
of GUI state; it also means the same request is what
:meth:`Layouts.render` runs inline. The job service the two job forms submit
through is the layouts service's own, over the plugin's scope and the host's
worker backend: a plugin that declares no ``jobs`` of its own still gets a
progress bar and a cancel button for an export, and the host pumps one more
service instead of two more registries.

*Progress is per page, and cancellation is checked between pages.* An atlas
reports ``covered / total`` after each page and the export reports once when the
file is committed, because a renderer that cannot stop mid-page must not claim
to. A cancelled job stops before the next page and raises
``QgisSdkJobCancelledError``; the file it was writing is not published
(decision-21: a request, never an interruption).

*A single image holds a single page.* PNG and SVG export one page, so a
multi-page layout is refused for those two formats by name; PDF carries all of
its pages and an atlas writes one page per feature.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from qgis_sdk.models import (
    LAYOUT_FORMATS,
    AtlasExport,
    AtlasPage,
    AtlasRequest,
    FileRef,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    LayoutSettings,
    QgisSdkExportRefusedError,
    QgisSdkJobCancelledError,
)
from qgis_sdk.services.contracts import Cancellation, Progress


class JobHandle(Protocol):
    """What the two job forms answer, as far as this layer may know it.

    The concrete ``qgis_sdk.jobs.JobHandle`` is a higher layer than the service
    protocols, so the job forms declare the surface a caller reads - the id, the
    status, the result and the cancel request - and the runtime's handle
    satisfies it structurally. Nothing here constructs one; only
    :mod:`qgis_sdk.layouts` submits work.
    """

    @property
    def id(self) -> str:
        """The attempt's id, ``layouts.export#1`` and so on."""
        ...

    @property
    def status(self) -> Any:
        """The attempt's state: queued, running, succeeded, failed or cancelled."""
        ...

    @property
    def result(self) -> Any:
        """The settled job's typed result; raises for a failed or cancelled one."""
        ...

    def cancel(self) -> bool:
        """Ask the job to stop; answer whether it was still active."""
        ...


__all__ = [
    "ATLAS_JOB_ID",
    "EXPORT_JOB_ID",
    "LayoutBackend",
    "Layouts",
    "NullCancellation",
    "NullProgress",
    "atlas_pages",
    "exported",
    "free_layout_name",
    "page_path",
    "stop_if_cancelled",
]

#: The declaration ids the two job forms submit under. One name each, so the
#: task manager shows "Export a layout" for every export and the handle's id
#: reads ``layouts.export#2`` for the second one a session submits.
EXPORT_JOB_ID = "layouts.export"
ATLAS_JOB_ID = "layouts.atlas"

#: The pattern's placeholders, checked before a render starts: an unknown name
#: is a caller's typo and is refused by name rather than written into a file.
_PATTERN_TOKENS = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}")


class NullProgress:
    """A ``Progress`` for a render nobody is watching; every report is dropped."""

    __slots__ = ()

    def report(self, fraction: float) -> None:
        """Accept and ignore one fraction."""
        del fraction


class NullCancellation:
    """A ``Cancellation`` for a render nobody can cancel."""

    __slots__ = ()

    def is_cancelled(self) -> bool:
        """Never cancelled: a blocking render runs to its end."""
        return False


@runtime_checkable
class LayoutBackend(Protocol):
    """What an adapter must answer for :class:`LayoutService` to sit on it.

    The two driving-thread methods read and edit the project's layout manager;
    the two render methods are handed a plain request and the job's seams, and
    may run on a worker. Nothing here carries a live layout across the
    boundary, which is what lets the fake and the native adapter be held to one
    contract.
    """

    def list(self) -> tuple[LayoutInfo, ...]:
        """Every print layout the project holds."""
        ...

    def load_template(self, template: Path) -> LayoutInfo:
        """Load a ``.qpt`` template into the project and describe the layout."""
        ...

    def render(
        self,
        request: LayoutRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> LayoutExport:
        """Write the layout to ``request.destination`` under the export policy."""
        ...

    def render_atlas(
        self,
        request: AtlasRequest,
        *,
        progress: Progress,
        cancellation: Cancellation,
    ) -> AtlasExport:
        """Write one file per coverage feature into ``request.directory``."""
        ...


class Layouts(Protocol):
    """Print layouts and atlases (TASK-89, decision-54 point 3).

    Every method raises ``QgisSdkLayoutNotFoundError`` for a name the project
    does not hold, ``QgisSdkExportRefusedError`` for a destination or format the
    export policy refuses (before anything is written, with every reason at
    once), and ``QgisSdkExportFailedError`` when the renderer failed after it
    started. ``QgisSdkUnsupportedCapabilityError`` is the answer on a host that
    cannot render layouts at all.
    """

    @property
    def jobs(self) -> Any:
        """The job service the two job forms submit through.

        A host pumps it beside the plugin's own ``ctx.jobs``: the export jobs
        are declared here rather than in the plugin's registry, so a plugin that
        declares no jobs of its own still gets one task per export.
        """
        ...

    def list(self) -> tuple[LayoutInfo, ...]:
        """Every print layout in the project, in the manager's order."""
        ...

    def load_template(self, template: FileRef) -> LayoutInfo:
        """Load a print-layout template file into the project.

        ``template`` is a ref the host minted for a ``.qpt`` file. The layout is
        added under the template *file's* name: a ``.qpt`` carries no name of its
        own, so ``report.qpt`` loads as a layout called ``report``. A name the
        project already holds gains a numeric suffix (``report (2)``), so
        loading a template never replaces a layout the user composed.
        """
        ...

    def export(
        self,
        layout: str,
        *,
        format: str = "pdf",
        destination: FileRef | None = None,
        settings: LayoutSettings | None = None,
        overwrite: bool = False,
    ) -> JobHandle:
        """Export ``layout`` as a job and answer its handle.

        The outcome is a :class:`~qgis_sdk.models.LayoutExport`; ``overwrite``
        decides whether an existing destination is replaced or refused.
        """
        ...

    def render(
        self,
        layout: str,
        *,
        format: str = "pdf",
        destination: FileRef | None = None,
        settings: LayoutSettings | None = None,
        overwrite: bool = False,
    ) -> LayoutExport:
        """Export ``layout`` and wait for the file: the same work, no job."""
        ...

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
        """Run ``layout``'s atlas as a job, one file per coverage feature.

        ``pattern`` names each file without its suffix and may use ``{index}``
        and ``{feature_id}``; the default is ``page-001.pdf`` and so on.
        """
        ...

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
        """Run ``layout``'s atlas and wait for every file: the same work, no job."""
        ...


def _slug(name: str) -> str:
    """A file-name-safe form of a layout name, for a host-chosen output."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-._")
    return cleaned or "layout"


def free_layout_name(taken: Iterable[str], name: str) -> str:
    """An unused layout name: ``name``, then ``name (2)``, ``name (3)`` and so on.

    A template load adds a layout, it never replaces one the user composed, so a
    name already in the project gains a numeric suffix - the answer the print
    designer's own duplicate-name dialog gives. Shared, so the fake and the
    native adapter answer the same list of names.
    """
    existing = set(taken)
    if name not in existing:
        return name
    number = 2
    while f"{name} ({number})" in existing:
        number += 1
    return f"{name} ({number})"


def _check_pattern(pattern: str) -> str:
    """Refuse an atlas pattern naming a placeholder the render cannot fill."""
    unknown = sorted(
        {
            token
            for token in _PATTERN_TOKENS.findall(pattern)
            if token not in ("index", "feature_id")
        }
    )
    if unknown:
        raise QgisSdkExportRefusedError(
            pattern,
            [
                (
                    f"unknown atlas pattern field(s) {', '.join(unknown)}; "
                    "a pattern may use {index} and {feature_id}"
                )
            ],
        )
    return pattern


def exported(request: LayoutRequest, written: Path, *, pages: int) -> LayoutExport:
    """Describe a finished export from the file it wrote.

    Shared by both backends so the size a caller reads is a fact about the file
    rather than a number a renderer remembers: a writer that counts its own
    bytes is a second source of truth, and the one on disk is the one that
    matters.
    """
    return LayoutExport(
        path=str(written),
        format=request.format,
        pages=pages,
        bytes=written.stat().st_size,
    )


def atlas_pages(
    request: AtlasRequest, written: list[tuple[int, int | None, Path]]
) -> AtlasExport:
    """Describe a finished atlas run from the files it wrote, in coverage order."""
    return AtlasExport(
        directory=request.directory,
        format=request.format,
        pages=tuple(
            AtlasPage(index=index, feature_id=feature_id, path=str(path))
            for index, feature_id, path in written
        ),
    )


def page_path(request: AtlasRequest, *, index: int, feature_id: int | None) -> Path:
    """The file name one atlas page gets: the pattern, filled, plus the suffix.

    Shared so a caller reading the pattern and the files on disk sees the same
    names on both backends; ``index`` is the page number a user counts from one,
    which is what ``{index:03d}`` in a pattern means.
    """
    name = request.pattern.format(index=index, feature_id=feature_id)
    return Path(request.directory) / f"{name}{LAYOUT_FORMATS[request.format]}"


def stop_if_cancelled(cancellation: Cancellation) -> None:
    """Raise the SDK's cancellation error if the job was asked to stop.

    Called between pages, which is the granularity a render can honour: a page
    already being drawn finishes, and the files already written stay written
    because each one is a finished file rather than a partial one. The id is
    the worker's own and stays zero: the scheduler settles the job as cancelled
    from the error's type (decision-21).
    """
    if cancellation.is_cancelled():
        raise QgisSdkJobCancelledError(0)
