"""In-memory service fakes: the same contracts the native adapters implement.

Fakes exist so pure tests can exercise a workflow without QGIS, and so the
contract suite can hold a fake and the future native adapter to identical
expectations (TASK-25.1). They are not emulators: they store what the contract
observes and no more.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    GeometryType,
    QgisSdkLayerNotFoundError,
    QgisSdkStyleIncompatibleError,
    VectorLayerInfo,
)
from qgis_sdk.resources import require_style
from qgis_sdk.services import Layers

__all__ = [
    "FakeLayers",
    "FakeProject",
    "FakeSettings",
    "FakeStyles",
    "RecordingNotifications",
]


class FakeLayers:
    """A ``Layers`` backend over datasets declared in the test.

    The fake carries an owner scope like every real backend, so a pure test can
    prove the same disposal rules the native adapter must honour.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._datasets: dict[str, dict[str, object]] = {}
        self._layers: dict[str, VectorLayerInfo] = {}
        self._selections: dict[str, tuple[int, ...]] = {}
        scope.on_close(self._release)

    def register(
        self,
        source: Path,
        *,
        name: str,
        geometry_type: GeometryType,
        field_names: Sequence[str],
        crs: str | None = None,
    ) -> None:
        """Declare a dataset this fake can open; setup, not part of the contract."""
        self._datasets[str(source)] = {
            "name": name,
            "geometry_type": geometry_type,
            "field_names": tuple(field_names),
            "crs": crs,
        }

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
        self._selections[layer_id] = ()
        return info

    def list_layers(self) -> tuple[VectorLayerInfo, ...]:
        """Return opened layers in the order they were opened."""
        self._scope.ensure_open()
        return tuple(self._layers.values())

    def layer(self, layer_id: str) -> VectorLayerInfo:
        """Return one opened layer."""
        self._scope.ensure_open()
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

    def _release(self) -> None:
        self._layers.clear()
        self._selections.clear()

    def _require(self, layer_id: str) -> VectorLayerInfo:
        try:
            return self._layers[layer_id]
        except KeyError:
            raise QgisSdkLayerNotFoundError(layer_id) from None


class FakeProject:
    """A ``Project`` backend that records owned layer membership."""

    def __init__(self, layers: Layers, scope: ResourceScope) -> None:
        self._layers = layers
        self._scope = scope
        self._layer_ids: list[str] = []

    def layer_ids(self) -> tuple[str, ...]:
        """Return membership in the order layers were added."""
        self._scope.ensure_open()
        return tuple(self._layer_ids)

    def add_layer(self, layer_id: str) -> None:
        """Add an owned layer once; a repeat add is a no-op."""
        self._scope.ensure_open()
        self._layers.layer(layer_id)
        if layer_id not in self._layer_ids:
            self._layer_ids.append(layer_id)


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


class FakeStyles:
    """A ``Styles`` backend that validates with the shared catalog rule.

    It deliberately does not emulate rendering: it applies the same
    ``StyleSpec.incompatibilities`` decision the native adapter makes, then
    records the application so a pure test can observe it.
    """

    def __init__(self, layers: Layers, scope: ResourceScope) -> None:
        self._layers = layers
        self._scope = scope
        self._applied: dict[str, list[str]] = {}

    def apply_style(self, layer_id: str, style: str) -> None:
        """Validate the target, then record the application."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        spec = require_style(style)
        reasons = spec.incompatibilities(info)
        if reasons:
            raise QgisSdkStyleIncompatibleError(layer_id, style, reasons)
        self._applied.setdefault(layer_id, []).append(style)

    def applied(self, layer_id: str) -> tuple[str, ...]:
        """Return styles applied to a layer; observation, not part of the contract."""
        self._scope.ensure_open()
        self._layers.layer(layer_id)
        return tuple(self._applied.get(layer_id, ()))


class RecordingNotifications:
    """A ``Notifications`` backend that records the messages it was given."""

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        """Record an informational message."""
        self._scope.ensure_open()
        self.messages.append(message)
