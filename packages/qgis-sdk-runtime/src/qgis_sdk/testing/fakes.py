"""In-memory service fakes: the same contracts the native adapters implement.

Fakes exist so pure tests can exercise a workflow without QGIS, and so the
contract suite can hold a fake and the future native adapter to identical
expectations (TASK-25.1). They are not emulators: they store what the contract
observes and no more.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    LAYER_KINDS,
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    Catalogue,
    GeometryType,
    ProviderInfo,
    QgisSdkAlgorithmFailedError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkLayerNotFoundError,
    QgisSdkStyleIncompatibleError,
    RunResult,
    TypedRun,
    VectorExport,
    VectorLayerInfo,
    validate_parameters,
)
from qgis_sdk.processing.runs import coerce_run, output_class
from qgis_sdk.resources import require_style
from qgis_sdk.services import (
    Layers,
    LogBase,
    LogRecord,
    Notification,
    NotificationsBase,
)

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService
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


#: What ``script_run`` accepts: the outputs, or a function of the run.
ScriptedOutputs = Mapping[str, object] | Callable[[AlgorithmRun], Mapping[str, object]]


class FakeAlgorithms:
    """An ``Algorithms`` backend that runs nothing and returns declared outputs.

    ``list``/``describe`` answer from the shipped snapshot (or the
    ``catalogue`` the test passes, e.g. one generated from its own QGIS);
    ``run`` answers from outputs the test scripted with :meth:`script_run`
    and records every :class:`AlgorithmRun` in :attr:`runs`, so a pure test
    can prove what an algorithm asked for as well as what it did with the
    answer. Validation is the real one (``validate_parameters`` over the
    catalogue), so a request the host would refuse is refused here too. It
    deliberately does not decide whether a working CRS is projected: that
    needs a CRS database the fake does not have, so the check belongs to the
    native adapter and its own test rather than to a guess here.
    """

    def __init__(
        self,
        layers: FakeLayers,
        scope: ResourceScope,
        *,
        catalogue: Catalogue | None = None,
        files: FilesService | None = None,
    ) -> None:
        self._layers = layers
        self._scope = scope
        self._catalogue = catalogue
        self._files = files
        self.requests: list[AlgorithmRequest] = []
        self.runs: list[AlgorithmRun] = []
        self._outputs: dict[type, Path] = {}
        self._scripted: dict[str, list[tuple[ScriptedOutputs, bool]]] = {}

    # -- setup, not part of the contract ----------------------------------

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

    def script_run(
        self,
        algorithm_id: str,
        outputs: ScriptedOutputs,
        *,
        repeat: bool = True,
    ) -> None:
        """Declare what the next ``run`` of ``algorithm_id`` produces.

        ``outputs`` maps output names to values, or is a callable taking the
        :class:`AlgorithmRun` and returning that mapping. A ``Path`` under a
        vector output is opened through the fake layers (register it first);
        a ``Path`` under a file output is granted through ``files`` and comes
        back as a ``FileRef``; anything else is returned as given. With
        ``repeat=False`` the answer is consumed by one run.
        """
        self._scripted.setdefault(algorithm_id, []).append((outputs, repeat))

    # -- the contract ------------------------------------------------------

    @property
    def catalogue(self) -> Catalogue:
        if self._catalogue is None:
            from qgis_sdk.processing.snapshot import core_catalogue

            self._catalogue = core_catalogue()
        return self._catalogue

    def providers(self) -> tuple[ProviderInfo, ...]:
        self._scope.ensure_open()
        return self.catalogue.providers

    def list(self, provider: str | None = None) -> tuple[AlgorithmInfo, ...]:
        self._scope.ensure_open()
        if provider is None:
            return self.catalogue.algorithms
        return self.catalogue.by_provider(provider)

    def describe(self, algorithm_id: str) -> AlgorithmInfo:
        self._scope.ensure_open()
        return self.catalogue.algorithm(algorithm_id)

    def run(
        self,
        request: AlgorithmRun | TypedRun | str,
        params: Mapping[str, object] | None = None,
    ) -> RunResult:
        """Validate like the host, record the run, answer from the script."""
        self._scope.ensure_open()
        run = coerce_run(request, params)
        info = self.describe(run.algorithm)
        validate_parameters(info, run.params)
        for parameter in info.parameters:
            value = run.params.get(parameter.name)
            if value is None or parameter.kind not in LAYER_KINDS:
                continue
            # Same rule as the native adapter: an owned layer id, a ref, or
            # an existing path; anything else is an unknown layer.
            if isinstance(value, str) and not Path(value).exists():
                self._layers.layer(value)
        self.runs.append(run)
        answer = self._next_answer(run)
        outputs: dict[str, object] = {}
        for name, value in answer.items():
            kind = output_class(info, name)
            if isinstance(value, Path):
                if kind == "vector":
                    value = self._layers.open_vector(value)
                elif kind == "directory":
                    value = self._file_service().grant_directory(value)
                elif kind == "file":
                    value = self._file_service().grant_file(value)
            outputs[name] = value
        return RunResult(algorithm=run.algorithm, outputs=outputs)

    def _next_answer(self, run: AlgorithmRun) -> Mapping[str, object]:
        queue = self._scripted.get(run.algorithm) or []
        if not queue:
            raise QgisSdkAlgorithmFailedError(
                run.algorithm,
                "no scripted outputs; call FakeAlgorithms.script_run() in the test",
            )
        outputs, repeat = queue[0]
        if not repeat:
            queue.pop(0)
        return outputs(run) if callable(outputs) else outputs

    def _file_service(self) -> FilesService:
        if self._files is None:
            from .files import FakeFiles

            self._files = FakeFiles(self._scope, owner="plugin:fake-algorithms")
        return self._files

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


class RecordingNotifications(NotificationsBase):
    """A ``Notifications`` backend that records what it was given.

    ``messages`` is every message text in order, whatever its level - the
    assertion most tests want; ``records`` keeps the level and the button
    ``with_action`` attached, so a test can press it with :meth:`press`.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self.messages: list[str] = []
        self.records: list[Notification] = []
        self._dispatch: list[Callable[..., object] | None] = [None]

    def bind_actions(self, dispatch: Callable[..., object]) -> None:
        """Make :meth:`press` run ``dispatch(action_id, **arguments)``."""
        self._dispatch[0] = dispatch

    def press(self, index: int = -1) -> object:
        """Press the button of the ``index``-th record, as the user would."""
        record = self.records[index]
        if record.action is None:
            raise ValueError(f"notification {record.message!r} carries no action")
        dispatch = self._dispatch[0]
        if dispatch is None:
            raise ValueError(
                "no actions bound: call bind_actions(runtime.actions...) first"
            )
        return dispatch(record.action.action_id, **record.action.arguments)

    def _deliver(self, notification: Notification) -> None:
        self._scope.ensure_open()
        self.messages.append(notification.message)
        self.records.append(notification)


class RecordingLog(LogBase):
    """A ``Log`` backend that keeps every record it was given.

    ``records`` is the full :class:`LogRecord` list in order; ``messages``
    the message texts alone, whatever their level. ``plugin`` is the tag
    the records carry, ``"test"`` unless a test names its plugin.
    """

    def __init__(self, scope: ResourceScope, plugin: str = "test") -> None:
        super().__init__(plugin)
        self._scope = scope
        self.records: list[LogRecord] = []

    @property
    def messages(self) -> list[str]:
        """The message text of every record, in order."""
        return [record.message for record in self.records]

    def _deliver(self, record: LogRecord) -> None:
        self._scope.ensure_open()
        self.records.append(record)


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
