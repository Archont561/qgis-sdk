"""The Processing classes and names the kind tables point at.

Both directions of a toolbox run read these: a declared kind names the widget
that collects it and the output class that reports it, and a result kind names
the destination parameter the dialog offers. They live in one module so a kind
added to ``qgis_sdk.models`` has one place to land here.
"""

from __future__ import annotations

from typing import Any

from qgis.core import (
    QgsProcessingOutputBoolean,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputHtml,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingOutputNumber,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterColor,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)

#: The name the dialog's one destination parameter has, and the output that
#: reports it; every result kind shares them except a multiple-layers output.
OUTPUT_PARAMETER = "OUTPUT"

#: The result name of a multiple-layers output, which writes into a folder and
#: so reports under a name of its own.
MULTI_OUTPUT_NAME = "OUTPUTS"

#: The Processing parameter classes the kind registry names, by class name.
#: A kind naming a class absent here fails the registry test, not a toolbox.
_PARAMETER_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        QgsProcessingParameterBoolean,
        QgsProcessingParameterColor,
        QgsProcessingParameterCrs,
        QgsProcessingParameterEnum,
        QgsProcessingParameterField,
        QgsProcessingParameterFile,
        QgsProcessingParameterMapLayer,
        QgsProcessingParameterNumber,
        QgsProcessingParameterRasterLayer,
        QgsProcessingParameterString,
        QgsProcessingParameterVectorLayer,
    )
}

#: The Processing output classes the result kind table names, by class name.
#: A kind naming a class absent here fails the registry test, not a toolbox.
_OUTPUT_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        QgsProcessingOutputBoolean,
        QgsProcessingOutputFile,
        QgsProcessingOutputFolder,
        QgsProcessingOutputHtml,
        QgsProcessingOutputMultipleLayers,
        QgsProcessingOutputNumber,
        QgsProcessingOutputRasterLayer,
        QgsProcessingOutputString,
        QgsProcessingOutputVectorLayer,
    )
}

#: Where a run of each result kind writes: the destination parameter class the
#: dialog offers and its options. A kind absent here (number, string, boolean)
#: hands its result back as a value with no destination to choose.
_DESTINATION_CLASSES: dict[str, tuple[type, dict[str, Any]]] = {
    "outputVector": (QgsProcessingParameterFeatureSink, {}),
    "outputRaster": (QgsProcessingParameterRasterDestination, {}),
    "outputFile": (QgsProcessingParameterFileDestination, {}),
    "outputFolder": (QgsProcessingParameterFolderDestination, {}),
    "outputHtml": (
        QgsProcessingParameterFileDestination,
        {"fileFilter": "HTML files (*.html)"},
    ),
    "outputMultilayer": (QgsProcessingParameterFolderDestination, {}),
}

#: The ``Qgis::ProcessingSourceType`` a map-layer parameter is narrowed to, per
#: layer kind.
#:
#: QGIS 3.44 has a parameter class of its own only for a vector and for a raster
#: layer; the other kinds exist as *source types*, which is what
#: ``QgsProcessingParameterMapLayer.setDataTypes`` restricts a parameter to. So a
#: mesh input is a map-layer parameter narrowed to ``Mesh`` rather than a
#: ``QgsProcessingParameterMeshLayer`` class that no QGIS release has. A tiled
#: scene is deliberately absent: ``Qgis::ProcessingSourceType`` gains
#: ``TiledScene`` only in QGIS 4.0, so that input stays an unrestricted
#: map-layer parameter - a restriction the running Processing does not know would
#: refuse the toolbox silently.
_LAYER_SOURCE_TYPES: dict[str, str] = {
    "mesh": "Mesh",
    "point_cloud": "PointCloud",
    "vector_tile": "VectorTile",
    "annotation": "Annotation",
}
