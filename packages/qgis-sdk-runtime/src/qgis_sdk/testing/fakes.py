"""In-memory service fakes: the same contracts the native adapters implement.

Fakes exist so pure tests can exercise a workflow without QGIS, and so the
contract suite can hold a fake and the future native adapter to identical
expectations (TASK-25.1). They are not emulators: they store what the contract
observes and no more.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    AlgorithmRequest,
    GeometryType,
    QgisSdkAlgorithmRejectedError,
    QgisSdkLayerNotFoundError,
    QgisSdkStyleIncompatibleError,
    VectorExport,
    VectorLayerInfo,
)
from qgis_sdk.resources import require_style
from qgis_sdk.services import Layers

if TYPE_CHECKING:
    from qgis_sdk.providers import Provider

__all__ = [
    "FakeAlgorithms",
    "FakeLayers",
    "FakeProcessing",
    "FakeProject",
    "FakeSettings",
    "FakeStyles",
    "RecordingNotifications",
]


class FakeAlgorithms:
    """An ``Algorithms`` backend that runs nothing and returns declared outputs.

    It records every request, so a pure test can prove what an algorithm asked
    for as well as what it did with the answer. It deliberately does not decide
    whether a working CRS is projected: that needs a CRS database the fake does
    not have, so the check belongs to the native adapter and its own test rather
    than to a guess here.
    """

    def __init__(self, layers: FakeLayers, scope: ResourceScope) -> None:
        self._layers = layers
        self._scope = scope
        self.requests: list[AlgorithmRequest] = []
        self._outputs: dict[type, Path] = {}

    def declare_output(
        self,
        request_type: type,
        source: Path,
        *,
        name: str,
        geometry_type: GeometryType,
        field_names: Sequence[str],
        crs: str | None = None,
    ) -> None:
        """Declare what a request type produces; setup, not part of the contract."""
        self._layers.register(
            source,
            name=name,
            geometry_type=geometry_type,
            field_names=field_names,
            crs=crs,
        )
        self._outputs[request_type] = source

    def execute(self, request: AlgorithmRequest) -> VectorLayerInfo:
        """Record the request and open the output declared for its type."""
        self._scope.ensure_open()
        # The source has to be a layer this runtime owns, exactly as the native
        # adapter requires before it can hand the source to Processing.
        self._layers.layer(request.layer_id)
        self.requests.append(request)
        declared = self._outputs.get(type(request))
        if declared is None:
            raise QgisSdkAlgorithmRejectedError(
                "execute", [f"no output declared for {type(request).__name__}"]
            )
        return self._layers.open_vector(declared)


_EMPTY_COLLECTION = '{"type": "FeatureCollection", "features": []}\n'


class FakeLayers:
    """A ``Layers`` backend over datasets declared in the test.

    The fake carries an owner scope like every real backend, so a pure test can
    prove the same disposal rules the native adapter must honour.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._datasets: dict[str, dict[str, object]] = {}
        self._layers: dict[str, VectorLayerInfo] = {}
        self._sources: dict[str, Path] = {}
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
        self._sources[layer_id] = Path(source)
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

        def write(partial: Path) -> None:
            if source.is_file():
                shutil.copyfile(source, partial)
            else:
                partial.write_text(_EMPTY_COLLECTION, encoding="utf-8")

        export_policy.run_export(plan, write)
        return VectorExport(path=str(plan.destination), driver=plan.driver)

    def _release(self) -> None:
        self._layers.clear()
        self._sources.clear()
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


class FakeProviderRegistration:
    """One provider a :class:`FakeProcessing` currently advertises."""

    def __init__(self, registry: FakeProcessing, provider: Provider) -> None:
        self._registry = registry
        self.provider = provider

    def unregister(self) -> None:
        """Take the provider down; a second call is a safe no-op."""
        self._registry._remove(self.provider.id, self)


class FakeProcessing:
    """A ``Processing`` registry that records what a host would advertise.

    It holds no toolbox, so it proves only the contract ``PluginRuntime``
    relies on: ``register_provider`` records the provider under its id,
    refuses a second registration of the same id by name - the way the QGIS
    registry refuses a duplicate provider - and ``unregister`` on the returned
    registration removes it again. ``registered`` is the ids currently held,
    in registration order; ``events`` is the full history a test can assert
    ordering against.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._live: dict[str, FakeProviderRegistration] = {}
        self.events: list[tuple[str, str]] = []

    @property
    def registered(self) -> tuple[str, ...]:
        """The ids of the providers currently advertised."""
        return tuple(self._live)

    def provider(self, provider_id: str) -> Provider:
        """Return the provider advertised under ``provider_id``."""
        return self._live[provider_id].provider

    def register_provider(self, provider: Provider) -> FakeProviderRegistration:
        """Advertise ``provider``, refusing an id that is already live."""
        self._scope.ensure_open()
        if provider.id in self._live:
            raise QgisSdkDeclarationError(
                f"provider {provider.id!r} is already registered with the host"
            )
        registration = FakeProviderRegistration(self, provider)
        self._live[provider.id] = registration
        self.events.append(("register", provider.id))
        return registration

    def _remove(self, provider_id: str, registration: FakeProviderRegistration) -> None:
        if self._live.get(provider_id) is registration:
            del self._live[provider_id]
            self.events.append(("unregister", provider_id))
