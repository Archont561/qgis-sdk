from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AnnotationLayerInfo,
    LayerInfo,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    VectorExport,
    VectorLayerInfo,
)
from qgis_sdk.testing.rasters import FakeRasters

from ._algorithms import (
    EMPTY_COLLECTION,
    OtherKindLayers,
    other_dataset,
    vector_dataset,
)
from ._declarations import OtherLayerDeclaration, VectorLayerDeclaration


class FakeLayers(OtherKindLayers):
    """A ``Layers`` backend over datasets declared in the test.

    The fake carries an owner scope like every real backend, so a pure test can
    prove the same disposal rules the native adapter must honour. The four
    non-vector kinds are opened by the inherited ``OtherKindLayers`` reader.
    """

    def __init__(
        self, scope: ResourceScope, *, rasters: FakeRasters | None = None
    ) -> None:
        self._scope = scope
        self._datasets: dict[str, dict[str, object]] = {}
        self._layers: dict[str, VectorLayerInfo] = {}
        #: Layers of the five other kinds TASK-91 adds, in the order opened, and
        #: the annotation layers a scenario declared before opening one.
        self._others: dict[str, LayerInfo] = {}
        self._annotations: dict[str, AnnotationLayerInfo] = {}
        self._annotation_names: set[str] = set()
        self._sources: dict[str, Path] = {}
        self._export_sources: dict[str, export_policy.SourceIdentity | None] = {}
        self._selections: dict[str, tuple[int, ...]] = {}
        #: The sibling raster fake, when the test built one: ``list_layers``
        #: then answers both kinds and a raster id reaching a vector-only
        #: method is refused by name, exactly as the native adapter does.
        self._rasters = rasters
        scope.on_close(self._release)

    def register(self, declaration: VectorLayerDeclaration) -> None:
        """Declare a vector dataset; ``dataset_path`` models a container URI."""
        self._datasets[str(declaration.source)] = vector_dataset(declaration)

    def register_layer(self, declaration: OtherLayerDeclaration) -> None:
        """Declare a mesh, point cloud, vector tile or tiled scene dataset."""
        self._datasets[str(declaration.source)] = other_dataset(declaration)

    def register_annotation(
        self, name: str, *, item_count: int = 0, crs: str | None = None
    ) -> None:
        """Declare what opening the annotation layer ``name`` answers.

        An annotation layer has no dataset to open, so what a test declares is
        the layer a project already holds - its items and its CRS - and opening
        an undeclared name creates an empty one.
        """
        AnnotationLayerInfo(id="declared", name=name, item_count=item_count, crs=crs)
        self._annotations[name] = AnnotationLayerInfo(
            id="declared", name=name, item_count=item_count, crs=crs
        )

    def open_annotation(self, name: str) -> AnnotationLayerInfo:
        """Create an annotation layer, empty unless the test declared one."""
        self._scope.ensure_open()
        layer_id = f"layer-{len(self._layers) + len(self._others) + 1}"
        declared = self._annotations.get(name)
        info = AnnotationLayerInfo(
            id=layer_id,
            name=name,
            item_count=0 if declared is None else declared.item_count,
            crs=None if declared is None else declared.crs,
        )
        self._others[layer_id] = info
        return info

    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Return a new layer for a declared dataset."""
        self._scope.ensure_open()
        declared = self._datasets.get(str(source))
        if declared is None:
            raise QgisSdkLayerNotFoundError(str(source))
        layer_id = f"layer-{len(self._layers) + 1}"
        info = VectorLayerInfo(
            id=layer_id,
            name=str(declared["name"]),
            geometry_type=declared["geometry_type"],  # type: ignore[arg-type]
            field_names=declared["field_names"],  # type: ignore[arg-type]
            crs=declared["crs"],  # type: ignore[arg-type]
        )
        self._layers[layer_id] = info
        dataset_path = Path(declared["source"])  # type: ignore[arg-type]
        captured = export_policy.capture_source(dataset_path, allow_virtual=True)
        self._export_sources[layer_id] = captured
        self._sources[layer_id] = (
            captured.path if captured is not None else dataset_path
        )
        self._selections[layer_id] = ()
        return info

    def list_layers(self) -> tuple[LayerInfo, ...]:
        """Return every opened layer, of both kinds, in the order opened."""
        self._scope.ensure_open()
        opened: list[LayerInfo] = list(self._layers.values())
        opened.extend(self._others.values())
        if self._rasters is not None:
            opened.extend(self._rasters.list_layers())
        return tuple(opened)

    def layer(self, layer_id: str) -> LayerInfo:
        """Return one opened layer, of either kind."""
        self._scope.ensure_open()
        if layer_id in self._others:
            return self._others[layer_id]
        if layer_id not in self._layers and self._rasters is not None:
            return self._rasters.raster(layer_id)
        return self._require(layer_id)

    def selection(self, layer_id: str) -> tuple[int, ...]:
        """Return the fake layer's current selection."""
        self._scope.ensure_open()
        self._require(layer_id)
        return self._selections[layer_id]

    def select(self, layer_id: str, feature_ids: Sequence[int]) -> None:
        """Set the selection; setup, because selection is a host action."""
        self._scope.ensure_open()
        self._require(layer_id)
        self._selections[layer_id] = tuple(feature_ids)

    def export_vector(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> VectorExport:
        """Copy the declared dataset to ``destination`` under the shared policy.

        The fake has no OGR, so the bytes are the source file's (or an empty
        feature collection when the declared source is not a real file, as a
        declared algorithm output is not); what it exercises is everything
        around the writer - refusal, staging, commit and cleanup - which is the
        contract a workflow depends on.
        """
        self._scope.ensure_open()
        self._require(layer_id)
        plan = export_policy.plan_export(destination, overwrite=overwrite)
        source = self._sources[layer_id]
        plan = export_policy.protect_source(plan, self._export_sources[layer_id])

        def write(partial: Path) -> None:
            if source.is_file():
                shutil.copyfile(source, partial)
            else:
                partial.write_text(EMPTY_COLLECTION, encoding="utf-8")

        export_policy.run_export(plan, write)
        return VectorExport(path=str(plan.destination), driver=plan.driver)

    def _release(self) -> None:
        self._layers.clear()
        self._others.clear()
        self._annotations.clear()
        self._sources.clear()
        self._export_sources.clear()
        self._selections.clear()

    def _require(self, layer_id: str) -> VectorLayerInfo:
        try:
            return self._layers[layer_id]
        except KeyError:
            pass
        other = self._others.get(layer_id)
        if other is not None:
            raise QgisSdkUnsupportedCapabilityError(
                layer_id,
                f"this layer is a {other.kind}; fields, features, styles and a "
                "vector export are vector work - read it through the service "
                f"its kind belongs to (ctx.rasters for a raster)",
            )
        if self._rasters is not None and layer_id in self._rasters.opened_layers():
            raise QgisSdkUnsupportedCapabilityError(
                layer_id,
                "this layer is a raster; fields, features, styles and a vector "
                "export are vector work - read it through ctx.rasters",
            )
        raise QgisSdkLayerNotFoundError(layer_id)


class FakeSettings:
    """A ``Settings`` backend over one in-memory dictionary.

    It carries an owner scope like the native adapter, so the same disposal
    contract holds for both backends.
    """

    def __init__(
        self,
        scope: ResourceScope,
        values: Mapping[str, str] | None = None,
    ) -> None:
        self._scope = scope
        self._values = dict(values or {})

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value, else the default."""
        self._scope.ensure_open()
        return self._values.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Store a value."""
        self._scope.ensure_open()
        self._values[key] = value
