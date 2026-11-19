"""The parts of a layout render both backends share: names, pages, cancellation.

A render is written once here and used by the fake and the native adapter, so
the names a caller reads on disk are the same on both: the file a finished
export describes is the file that was written, and an atlas page's name is the
pattern filled in rather than a second interpretation of it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from qgis_sdk.models import (
    LAYOUT_FORMATS,
    AtlasExport,
    AtlasPage,
    AtlasRequest,
    LayoutExport,
    LayoutRequest,
    QgisSdkExportRefusedError,
    QgisSdkJobCancelledError,
)
from qgis_sdk.services.contracts import Cancellation

__all__ = [
    "NullCancellation",
    "NullProgress",
    "atlas_pages",
    "check_pattern",
    "exported",
    "free_layout_name",
    "page_path",
    "slug",
    "stop_if_cancelled",
]

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


def slug(name: str) -> str:
    """A file-name-safe form of a layout name, for a host-chosen output."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-._")
    return cleaned or "layout"


def free_layout_name(taken: Iterable[str], name: str) -> str:
    """An unused layout name: ``name``, then ``name (2)``, ``name (3)`` and so on.

    A template load adds a layout, it never replaces one the user composed, so a
    name already in the project gains a numeric suffix - the answer the print
    designer's own duplicate-name dialog gives. Shared, so the fake and the
    native adapter answer the same list of names.

    Args:
        taken: The names the project already holds.
        name: The name the caller asked for.

    Returns:
        That name, or its first free numbered form.
    """
    existing = set(taken)
    if name not in existing:
        return name
    number = 2
    while f"{name} ({number})" in existing:
        number += 1
    return f"{name} ({number})"


def check_pattern(pattern: str) -> str:
    """Refuse an atlas pattern naming a placeholder the render cannot fill.

    Args:
        pattern: The file-name pattern to check.
    """
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

    Args:
        request: The request that was rendered.
        written: The file the renderer wrote.
        pages: How many pages the format carries.
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
    """Describe a finished atlas run from the files it wrote, in coverage order.

    Args:
        request: The request that was rendered.
        written: Each page's index, feature id and file, in coverage order.
    """
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

    Args:
        request: The atlas request whose pattern and format apply.
        index: The page number, counting from one.
        feature_id: The coverage feature it draws, when the layer has ids.
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

    Args:
        cancellation: The signal to read.
    """
    if cancellation.is_cancelled():
        raise QgisSdkJobCancelledError(0)
