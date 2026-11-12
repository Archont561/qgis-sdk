"""Template loading, layout description, export settings, and the write itself."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from qgis_sdk.models import (
    AtlasInfo,
    AtlasRequest,
    LayoutInfo,
    LayoutRequest,
    QgisSdkExportFailedError,
    QgisSdkExportRefusedError,
    QgisSdkJobCancelledError,
)

__all__ = ["describe", "settings", "template_document", "write"]


def template_document(template: Path) -> Any:
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


def describe(layout: Any) -> LayoutInfo:
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


def settings(core: Any, request: LayoutRequest | AtlasRequest) -> Any:
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


def write(
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
