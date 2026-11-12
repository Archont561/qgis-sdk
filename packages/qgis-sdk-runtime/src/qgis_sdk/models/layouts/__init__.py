"""Print layouts and atlases, as a page and a plugin handler see them.

decision-54 point 3 asks for layouts as a curated service: list them, load a
template, export one to a file as a job, and iterate an atlas with progress. The
shapes here are what crosses that boundary, and five choices are deliberate.

*A layout is named by its own name.* ``QgsLayoutManager`` keeps layout names
unique in a project, so the name is already an identifier. A second unique key
would be a second thing to keep in step, and a page would have to carry both to
be useful.

*An export is a file and a format, not a ``QgsLayoutExporter``.* The exporter is
the host's business; what a caller needs is where the bytes went and in which
format, so a finished export is :class:`LayoutExport` and nothing in this module
can render anything.

*PNG and SVG name one image, PDF holds many pages.* ``pages`` is the count of
pages in the file the export produced: a PDF carries every page of the layout, an
image carries exactly one, and an export of a multi-page layout to an image is
refused by the service rather than answered with a file name that quietly means
the first page.

*An atlas page names its feature.* ``feature_id`` is the id of the coverage
feature that page was drawn for - the one thing a caller can join the file back
to its record with.

*Progress and cancellation are the job's.* A render is handed the two
:class:`~qgis_sdk.services.contracts.Progress` and
:class:`~qgis_sdk.services.contracts.Cancellation` seams rather than inventing a
third, so an export reports to the bar its ``@job`` already owns and a cancelled
atlas stops between pages instead of after the last one.
"""

from __future__ import annotations

from ._formats import (
    ATLAS_EXPORT,
    ATLAS_INFO,
    ATLAS_PAGE,
    ATLAS_TOKENS,
    DEFAULT_ATLAS_PATTERN,
    LAYOUT_EXPORT,
    LAYOUT_FORMATS,
    LAYOUT_INFO,
    LAYOUT_SUFFIXES,
    SINGLE_PAGE_FORMATS,
)
from ._records import (
    AtlasExport,
    AtlasInfo,
    AtlasPage,
    AtlasRequest,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    LayoutSettings,
)

__all__ = [
    "ATLAS_EXPORT",
    "ATLAS_INFO",
    "ATLAS_PAGE",
    "ATLAS_TOKENS",
    "DEFAULT_ATLAS_PATTERN",
    "LAYOUT_EXPORT",
    "LAYOUT_FORMATS",
    "LAYOUT_INFO",
    "LAYOUT_SUFFIXES",
    "SINGLE_PAGE_FORMATS",
    "AtlasExport",
    "AtlasInfo",
    "AtlasPage",
    "AtlasRequest",
    "LayoutExport",
    "LayoutInfo",
    "LayoutRequest",
    "LayoutSettings",
]
