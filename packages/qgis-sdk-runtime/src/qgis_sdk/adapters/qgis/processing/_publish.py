"""Where a finished run's output lands, one way per result kind.

The function's result kind (the ``qgis_sdk.models`` output kind table) decides
where the result goes: a produced vector layer is copied feature by feature
into whatever sink the user chose, a produced raster or file is copied into the
chosen destination, a produced folder or several layers are written into the
chosen folder, a report is saved as its ``.html``, and a number, string or
boolean is handed back as the value itself. That keeps decision-19's "explicit
destination" and leaves the produced temporary artifacts untouched for the
caller's own cleanup.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsProcessingContext,
    QgsProcessingException,
    QgsVectorFileWriter,
)

from qgis_sdk.models import output_kinds

from ._services import files_of, rasters_of
from ._tables import MULTI_OUTPUT_NAME, OUTPUT_PARAMETER


@dataclass(frozen=True, slots=True)
class _Run:
    """One finished run: what the function produced, and where it has to go."""

    algorithm: Any
    bridge: Any
    result: Any
    parameters: dict
    context: QgsProcessingContext

    def destination(self) -> Path:
        """The destination the dialog chose, refused when it named none."""
        destination = self.algorithm.parameterAsFileOutput(
            self.parameters, OUTPUT_PARAMETER, self.context
        )
        if not destination:
            raise QgsProcessingException(f"{OUTPUT_PARAMETER} requires a destination")
        return Path(destination)


def _copy_file(run: _Run, source: Path) -> str:
    """Copy one produced file to the destination the dialog chose."""
    destination = run.destination()
    shutil.copyfile(source, destination)
    return str(destination)


def _copy_features(produced: Any, sink: Any) -> None:
    """Copy each feature so the destination owns its geometry and attributes."""
    for feature in produced.getFeatures():
        copy = QgsFeature(produced.fields())
        copy.setGeometry(feature.geometry())
        copy.setAttributes(feature.attributes())
        sink.addFeature(copy, QgsFeatureSink.FastInsert)


def _publish_vector(run: _Run) -> str:
    """Copy the produced layer's features into the destination QGIS asked for."""
    produced = run.bridge.layers._qgs_layer(run.result.id)
    sink, destination = run.algorithm.parameterAsSink(
        run.parameters,
        OUTPUT_PARAMETER,
        run.context,
        produced.fields(),
        produced.wkbType(),
        produced.crs(),
    )
    _copy_features(produced, sink)
    return destination


def _publish_raster(run: _Run) -> str:
    """Copy the produced raster file to the destination the dialog chose."""
    owned = rasters_of(run.bridge)._qgs_raster(run.result.id)
    return _copy_file(run, Path(owned.source()))


def _publish_ref(run: _Run, *, folder: bool) -> str:
    """Publish the file or folder a produced ref names.

    Never the ref's own borrowed path: decision-19 says the destination is
    explicit, so a produced file is copied to where the dialog pointed.
    """
    files = files_of(run.bridge)
    if files is None:
        raise QgsProcessingException(
            "this host has no files service, so a produced ref cannot be published"
        )
    source = Path(files.resolve(run.result, operation="read"))
    destination = run.destination()
    if folder:
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copyfile(source, destination)
    return str(destination)


def _publish_file(run: _Run) -> str:
    return _publish_ref(run, folder=False)


def _publish_folder(run: _Run) -> str:
    return _publish_ref(run, folder=True)


def _free_target(folder: Path, name: str) -> Path:
    """A file in ``folder`` that does not overwrite what is already there."""
    target = folder / f"{name}.gpkg"
    number = 2
    while target.exists():
        target = folder / f"{name}-{number}.gpkg"
        number += 1
    return target


def _write_layer(run: _Run, layer: Any, folder: Path) -> Path:
    """Write one produced layer into ``folder`` as a GeoPackage of its own."""
    produced = run.bridge.layers._qgs_layer(layer.id)
    target = _free_target(folder, layer.name or produced.name() or "layer")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = target.stem
    error, _new_name, message = QgsVectorFileWriter.writeAsVectorFormatV3(
        produced, str(target), run.context.transformContext(), options
    )
    if error:
        raise QgsProcessingException(
            f"cannot write {target.name}: {message or 'the writer refused'}"
        )
    return target


def _publish_layers(run: _Run) -> list[str]:
    """Write every produced layer into the chosen folder, one file each."""
    folder = run.destination()
    folder.mkdir(parents=True, exist_ok=True)
    return [str(_write_layer(run, layer, folder)) for layer in run.result]


def _publish_value(run: _Run) -> Any:
    """A number, string or boolean is its own result: there is nothing to place."""
    return run.result


#: Where a run of each result kind publishes to. A kind absent here has no
#: destination to write, so its result is handed back as the value itself.
_PUBLISHERS: dict[str, Callable[[_Run], Any]] = {
    "outputVector": _publish_vector,
    "outputRaster": _publish_raster,
    "outputFile": _publish_file,
    "outputHtml": _publish_file,
    "outputFolder": _publish_folder,
    "outputMultilayer": _publish_layers,
}


def published(run: _Run, result_kind: str) -> dict:
    """Hand the produced output to the destination its kind publishes to."""
    kind = output_kinds()[result_kind]
    name = MULTI_OUTPUT_NAME if kind.name == "outputMultilayer" else OUTPUT_PARAMETER
    return {name: _PUBLISHERS.get(kind.name, _publish_value)(run)}
