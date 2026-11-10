"""In-memory service fakes: the same contracts the native adapters implement.

Fakes exist so pure tests can exercise a workflow without QGIS, and so the
contract suite can hold a fake and the future native adapter to identical
expectations. They are not emulators: they store what the contract
observes and no more.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import qgis_sdk.exports as export_policy
from qgis_sdk.batch import batch_body, batch_items
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.jobs import JobHandle, JobService
from qgis_sdk.models import (
    LAYER_KINDS,
    STYLE_MANAGER_KINDS,
    SYMBOLS_FOR_GEOMETRY,
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    AnnotationLayerInfo,
    AuthConfiguration,
    CanvasExtent,
    Catalogue,
    ConnectionInfo,
    ConnectionItem,
    ConnectionTest,
    FileRef,
    FillSymbol,
    GeometryType,
    Labelling,
    LayerInfo,
    LineSymbol,
    MarkerSymbol,
    MeshLayerInfo,
    PointCloudLayerInfo,
    ProviderInfo,
    QgisSdkAlgorithmFailedError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkAuthConfigNotFoundError,
    QgisSdkConnectionItemNotFoundError,
    QgisSdkConnectionNotFoundError,
    QgisSdkLayerNotFoundError,
    QgisSdkStyleIncompatibleError,
    QgisSdkStyleTextError,
    QgisSdkUnsupportedCapabilityError,
    Renderer,
    RunResult,
    SingleSymbolRenderer,
    StyleEntry,
    StyleText,
    TiledSceneLayerInfo,
    TypedRun,
    VectorExport,
    VectorLayerInfo,
    VectorTileLayerInfo,
    renderer_from_wire,
    symbol_fits_geometry,
    validate_parameters,
)
from qgis_sdk.processing.runs import coerce_run, output_class, plan_destinations
from qgis_sdk.resources import require_style
from qgis_sdk.services import (
    Layers,
    LogBase,
    LogRecord,
    Notification,
    NotificationsBase,
)

from .project import FakeProject
from .rasters import FakeRasters

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService
    from qgis_sdk.providers import Provider

__all__ = [
    "ConnectionDeclaration",
    "DeclaredOutput",
    "FakeAlgorithmSetup",
    "FakeAlgorithms",
    "FakeLayers",
    "FakeProcessing",
    "FakeProject",
    "FakeSettings",
    "FakeStyles",
    "OtherLayerDeclaration",
    "RecordingNotifications",
    "TableDeclaration",
    "VectorLayerDeclaration",
]


#: What ``script_run`` accepts: the outputs, or a function of the run.
ScriptedOutputs = Mapping[str, object] | Callable[[AlgorithmRun], Mapping[str, object]]
#: A model's scripted answer: final values, or a callable from the ref and the
#: params it was run with - a model has no registry entry to script against.
ScriptedModelOutputs = (
    Mapping[str, object]
    | Callable[[FileRef, Mapping[str, object]], Mapping[str, object]]
)


@dataclass(frozen=True, slots=True)
class FakeAlgorithmSetup:
    """The collaborators one ``FakeAlgorithms`` backend is built from."""

    layers: FakeLayers
    scope: ResourceScope
    catalogue: Catalogue | None = None
    files: FilesService | None = None
    workers: Any | None = None


@dataclass(frozen=True, slots=True)
class DeclaredOutput:
    """What one ``AlgorithmRequest`` type produces, as a vector dataset."""

    request_type: type
    source: Path
    name: str
    geometry_type: GeometryType
    field_names: Sequence[str]
    crs: str | None = None


@dataclass(frozen=True, slots=True)
class VectorLayerDeclaration:
    """One vector dataset a ``FakeLayers`` backend can open."""

    source: Path
    name: str
    geometry_type: GeometryType
    field_names: Sequence[str]
    crs: str | None = None
    dataset_path: Path | None = None


@dataclass(frozen=True, slots=True)
class OtherLayerDeclaration:
    """One mesh, point-cloud, tile or scene dataset a ``FakeLayers`` can open."""

    source: Path
    name: str
    kind: str
    crs: str | None = None
    dataset_path: Path | None = None
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectionDeclaration:
    """One registered connection and the schemas it browses to."""

    name: str
    provider: str = "ogr"
    auth_config: str | None = None
    schemas: Sequence[str] = ()
    valid: bool = True
    message: str | None = None
    accepts_auth: bool = True


@dataclass(frozen=True, slots=True)
class TableDeclaration:
    """One table or view inside a declared connection."""

    connection: str
    name: str
    provider: str = "ogr"
    schema: str = ""
    kind: str = "vector"
    geometries: Sequence[str] = ()
    fields: Sequence[str] = ()
    crs: str | None = None


def _validate_run(algorithms, info, run) -> None:
    """Validate the params and layer inputs exactly as the host would."""
    validate_parameters(info, run.params)
    plan_destinations(
        info,
        run.params,
        lambda ref: algorithms._file_service().resolve(ref, operation="write"),
    )
    for parameter in info.parameters:
        value = run.params.get(parameter.name)
        if value is None or parameter.kind not in LAYER_KINDS:
            continue
        # Same rule as the native adapter: an owned layer id, a ref, or
        # an existing path; anything else is an unknown layer.
        if isinstance(value, str) and not Path(value).exists():
            algorithms._layers.layer(value)


def _open_vector_output(algorithms, value):
    return algorithms._layers.open_vector(value)


def _grant_directory_output(algorithms, value):
    return algorithms._file_service().grant_directory(value)


def _grant_file_output(algorithms, value):
    return algorithms._file_service().grant_file(value)


_PATH_OUTPUTS = {
    "vector": _open_vector_output,
    "directory": _grant_directory_output,
    "file": _grant_file_output,
}


def _path_output(algorithms, kind, value):
    resolver = _PATH_OUTPUTS.get(kind)
    return resolver(algorithms, value) if resolver is not None else value


def _output_value(algorithms, info, name, value):
    kind = output_class(info, name)
    if isinstance(value, Path):
        return _path_output(algorithms, kind, value)
    if kind == "layers" and isinstance(value, (list, tuple)):
        return tuple(
            algorithms._layers.open_vector(item) if isinstance(item, Path) else item
            for item in value
        )
    return value


def _resolve_outputs(algorithms, info, answer):
    return {
        name: _output_value(algorithms, info, name, value)
        for name, value in answer.items()
    }


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

    def __init__(self, setup: FakeAlgorithmSetup) -> None:
        self._layers = setup.layers
        self._scope = setup.scope
        self._catalogue = setup.catalogue
        self._files = setup.files
        self.requests: list[AlgorithmRequest] = []
        self.runs: list[AlgorithmRun] = []
        #: What ``run_model`` was asked: the model ref and its params
        #: (observation, like :attr:`runs`), so a test proves the params a
        #: caller sent. A pair rather than an :class:`AlgorithmRun` because a
        #: model file's name is not a registry id.
        self.model_runs: list[tuple[FileRef, dict[str, object]]] = []
        self._outputs: dict[type, Path] = {}
        self._scripted: dict[str, list[tuple[ScriptedOutputs, bool]]] = {}
        self._scripted_models: dict[str, list[tuple[ScriptedModelOutputs, bool]]] = {}
        self._jobs = JobService(setup.scope, workers=setup.workers)

    # -- setup, not part of the contract ----------------------------------

    def declare_output(self, output: DeclaredOutput) -> None:
        """Declare what a request type produces; setup, not part of the contract."""
        self._layers.register(
            VectorLayerDeclaration(
                output.source,
                name=output.name,
                geometry_type=output.geometry_type,
                field_names=output.field_names,
                crs=output.crs,
            )
        )
        self._outputs[output.request_type] = output.source

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

    def script_run_model(
        self,
        model: FileRef,
        outputs: ScriptedModelOutputs,
        *,
        repeat: bool = True,
    ) -> None:
        """Declare what the next ``run_model`` of ``model`` produces.

        A model has no registry entry to script against, so the answer is
        keyed by the ref's id and the values are the final ones - owned
        :class:`VectorLayerInfo`, :class:`FileRef` objects or scalars, exactly
        the shapes :class:`RunResult` describes. A callable takes the ref and
        the params of the run. With ``repeat=False`` the answer is consumed by
        one run.
        """
        self._scripted_models.setdefault(model.id, []).append((outputs, repeat))

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
        _validate_run(self, info, run)
        self.runs.append(run)
        answer = self._next_answer(run)
        outputs = _resolve_outputs(self, info, answer)
        return RunResult(algorithm=run.algorithm, outputs=outputs)

    def run_model(
        self, model: FileRef, params: Mapping[str, object] | None = None
    ) -> RunResult:
        """Record the run and answer from the script, keyed by the ref's id."""
        self._scope.ensure_open()
        if not isinstance(model, FileRef):
            raise QgisSdkAlgorithmRejectedError(
                "run_model",
                ["a model is a FileRef the host minted, not a path (decision-20)"],
            )
        recorded = dict(params or {})
        self.model_runs.append((model, recorded))
        queue = self._scripted_models.get(model.id) or []
        if not queue:
            raise QgisSdkAlgorithmFailedError(
                model.name,
                "no scripted outputs; call FakeAlgorithms.script_run_model() "
                "in the test",
            )
        outputs, repeat = queue[0]
        if not repeat:
            queue.pop(0)
        answer = outputs(model, recorded) if callable(outputs) else outputs
        return RunResult(algorithm=model.name, outputs=dict(answer))

    def batch(self, runs: Sequence[AlgorithmRun | TypedRun | str]) -> JobHandle:
        """Submit the batch as one job through this backend's job service."""
        self._scope.ensure_open()
        return self._jobs.bind(batch_body(self)).delay(runs=batch_items(runs))

    @property
    def jobs(self) -> JobService:
        """The job service ``batch`` submits through."""
        return self._jobs

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


#: How each kind's description is built from a declaration's fields. One table
#: rather than five branches, so "the fake accepts what the model accepts" is a
#: property of the file rather than of five places that could drift apart.
_OTHER_KINDS: dict[str, tuple[type, tuple[str, ...]]] = {
    "mesh": (MeshLayerInfo, ("vertex_count", "face_count", "group_count")),
    "point_cloud": (PointCloudLayerInfo, ("point_count", "attribute_names")),
    "vector_tile": (VectorTileLayerInfo, ("source_type", "min_zoom", "max_zoom")),
    "tiled_scene": (TiledSceneLayerInfo, ("extent",)),
}


def _detail(kind: str, detail: Mapping[str, object]) -> dict[str, object]:
    """The keyword arguments one kind's model takes, from a declaration.

    ``extent`` is accepted as the mapping a test writes down (four numbers) or
    as a box already built, because writing ``CanvasExtent(...)`` in every
    declaration would hide the numbers the test is about behind a constructor.
    """
    assert kind in _OTHER_KINDS, kind
    _model, fields = _OTHER_KINDS[kind]
    unknown = set(detail) - set(fields)
    if unknown:
        raise QgisSdkDeclarationError(
            f"a {kind} layer has no field {min(unknown)!r}; it declares "
            f"{', '.join(fields)}"
        )
    missing = [field for field in fields if field not in detail]
    if missing:
        raise QgisSdkDeclarationError(
            f"a {kind} layer declares {', '.join(fields)}; {missing[0]!r} is missing"
        )
    values = dict(detail)
    if kind == "tiled_scene" and isinstance(values["extent"], Mapping):
        values["extent"] = CanvasExtent(**values["extent"])  # type: ignore[arg-type]
    if kind == "point_cloud":
        values["attribute_names"] = tuple(values["attribute_names"])  # type: ignore[arg-type]
    return values


def _vector_dataset(declaration: VectorLayerDeclaration) -> dict[str, object]:
    """The stored shape of one declared vector dataset."""
    return {
        "kind": "vector",
        "source": Path(declaration.dataset_path)
        if declaration.dataset_path is not None
        else Path(declaration.source),
        "name": declaration.name,
        "geometry_type": declaration.geometry_type,
        "field_names": tuple(declaration.field_names),
        "crs": declaration.crs,
        "detail": {},
    }


def _other_dataset(declaration: OtherLayerDeclaration) -> dict[str, object]:
    """Validate one other-kind declaration and return its stored shape."""
    if declaration.kind not in _OTHER_KINDS:
        raise QgisSdkDeclarationError(
            f"{declaration.kind!r} is not a layer kind a declaration opens; "
            f"{', '.join(_OTHER_KINDS)} are"
        )
    fields = _detail(declaration.kind, declaration.detail)
    model, _names = _OTHER_KINDS[declaration.kind]
    model(
        id="declared",
        name=declaration.name,
        crs=declaration.crs,
        **fields,  # type: ignore[arg-type]
    )
    return {
        "kind": declaration.kind,
        "source": Path(declaration.dataset_path)
        if declaration.dataset_path is not None
        else Path(declaration.source),
        "name": declaration.name,
        "crs": declaration.crs,
        "detail": fields,
    }


class _OtherKindLayers:
    """The four non-vector layer kinds, opened through one shared reader."""

    def open_mesh(self, source: Path) -> MeshLayerInfo:
        """Return a new mesh layer for a declared mesh dataset."""
        return self._open_kind(source, "mesh")  # type: ignore[return-value]

    def open_point_cloud(self, source: Path) -> PointCloudLayerInfo:
        """Return a new point cloud layer for a declared point cloud dataset."""
        return self._open_kind(source, "point_cloud")  # type: ignore[return-value]

    def open_vector_tile(self, source: Path) -> VectorTileLayerInfo:
        """Return a new vector tile layer for a declared tile source."""
        return self._open_kind(source, "vector_tile")  # type: ignore[return-value]

    def open_tiled_scene(self, source: Path) -> TiledSceneLayerInfo:
        """Return a new tiled scene for a declared scene dataset."""
        return self._open_kind(source, "tiled_scene")  # type: ignore[return-value]

    def _open_kind(self, source: Path, kind: str) -> LayerInfo:
        """Open a declared dataset as ``kind``, or refuse it as missing.

        A dataset declared as another kind is *missing* rather than mistyped: on
        a native host the provider for ``kind`` is handed the file and answers an
        invalid layer, which is the same refusal a name nobody declared gets.
        """
        self._scope.ensure_open()
        declared = self._datasets.get(str(source))
        if declared is None or declared["kind"] != kind:
            raise QgisSdkLayerNotFoundError(str(source))
        model, _fields = _OTHER_KINDS[kind]
        layer_id = f"layer-{len(self._layers) + len(self._others) + 1}"
        info = model(
            id=layer_id,
            name=str(declared["name"]),
            crs=declared["crs"],  # type: ignore[arg-type]
            **declared["detail"],  # type: ignore[arg-type]
        )
        self._others[layer_id] = info
        return info


class FakeLayers(_OtherKindLayers):
    """A ``Layers`` backend over datasets declared in the test.

    The fake carries an owner scope like every real backend, so a pure test can
    prove the same disposal rules the native adapter must honour. The four
    non-vector kinds are opened by the inherited ``_OtherKindLayers`` reader.
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
        self._datasets[str(declaration.source)] = _vector_dataset(declaration)

    def register_layer(self, declaration: OtherLayerDeclaration) -> None:
        """Declare a mesh, point cloud, vector tile or tiled scene dataset."""
        self._datasets[str(declaration.source)] = _other_dataset(declaration)

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
                partial.write_text(_EMPTY_COLLECTION, encoding="utf-8")

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


class FakeStyles:
    """A ``Styles`` backend that validates with the shared catalog rule.

    It deliberately does not emulate *rendering*: it applies the same
    ``StyleSpec.incompatibilities`` decision the native adapter makes, then
    records the application so a pure test can observe it.

    The symbology half stores the description it was given and answers it back,
    which is what makes a round trip one assertion in a plugin's own tests; a
    layer nobody has styled answers the renderer its geometry implies, so a test
    that never set anything still reads a description rather than ``None``. QML
    and SLD are modelled as the same documented JSON document with a dialect on
    it: the fake round-trips *its own* text and refuses text it did not write,
    and the native adapter is where the real QGIS dialects are proven.
    """

    def __init__(
        self,
        layers: Layers,
        scope: ResourceScope,
        *,
        styles: Sequence[StyleEntry] = (),
    ) -> None:
        self._layers = layers
        self._scope = scope
        self._applied: dict[str, list[str]] = {}
        self._styles: list[StyleEntry] = list(styles)
        self._renderers: dict[str, Renderer] = {}
        self._labelling: dict[str, Labelling] = {}

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

    # -- symbology -----------------------------------------------------------

    def symbology(self, layer_id: str) -> Renderer:
        """Answer the renderer this backend holds for the layer."""
        info = self._vector(layer_id)
        stored = self._renderers.get(layer_id)
        if stored is not None:
            return stored
        return _default_renderer(info.geometry_type)

    def set_symbology(self, layer_id: str, renderer: Renderer) -> None:
        """Record a renderer, refusing a symbol its geometry cannot draw."""
        info = self._vector(layer_id)
        reason = symbol_fits_geometry(renderer, info.geometry_type)
        if reason is not None:
            raise QgisSdkStyleIncompatibleError(layer_id, renderer.kind, (reason,))
        self._renderers[layer_id] = renderer

    def labelling(self, layer_id: str) -> Labelling:
        """Answer the labelling this backend holds for the layer."""
        self._vector(layer_id)
        return self._labelling.get(layer_id, Labelling())

    def set_labelling(self, layer_id: str, labelling: Labelling) -> None:
        """Record a labelling."""
        self._vector(layer_id)
        self._labelling[layer_id] = labelling

    # -- the style manager and style text ------------------------------------

    def list_styles(self, kind: str | None = None) -> tuple[StyleEntry, ...]:
        """Answer the declared style entries, optionally of one kind."""
        self._scope.ensure_open()
        if kind is not None and kind not in STYLE_MANAGER_KINDS:
            raise ValueError(
                f"a style manager kind is one of {', '.join(STYLE_MANAGER_KINDS)}, "
                f"not {kind!r}"
            )
        return tuple(
            entry for entry in self._styles if kind is None or entry.kind == kind
        )

    def export_style(self, layer_id: str, format: str) -> StyleText:
        """Write the layer's renderer and labelling as this fake's document."""
        self._vector(layer_id)
        document = {
            "qgis_sdk_style": 1,
            "format": format,
            "renderer": self.symbology(layer_id).to_wire(),
            "labelling": self.labelling(layer_id).to_wire(),
        }
        return StyleText(format=format, text=json.dumps(document, sort_keys=True))

    def import_style(self, layer_id: str, text: str, format: str) -> None:
        """Read this fake's document back, refusing anything else."""
        info = self._vector(layer_id)
        try:
            document = json.loads(text)
        except ValueError as error:
            raise QgisSdkStyleTextError(format, str(error)) from None
        if not isinstance(document, dict) or document.get("qgis_sdk_style") != 1:
            raise QgisSdkStyleTextError(format, "not a style document this fake wrote")
        if document.get("format") != format:
            raise QgisSdkStyleTextError(
                format, f"the document is {document.get('format')!r}, not {format!r}"
            )
        renderer = renderer_from_wire(document["renderer"])
        reason = symbol_fits_geometry(renderer, info.geometry_type)
        if reason is not None:
            raise QgisSdkStyleIncompatibleError(layer_id, format, (reason,))
        self._renderers[layer_id] = renderer
        self._labelling[layer_id] = Labelling.from_wire(document["labelling"])

    def _vector(self, layer_id: str) -> VectorLayerInfo:
        """Return the layer, refusing one no renderer applies to."""
        self._scope.ensure_open()
        info = self._layers.layer(layer_id)
        if not isinstance(info, VectorLayerInfo):
            raise QgisSdkUnsupportedCapabilityError(
                info.id,
                f"a {info.kind} is drawn by QGIS, not by a renderer this SDK sets",
            )
        return info


def _default_renderer(geometry_type: str) -> Renderer:
    """The renderer a layer of ``geometry_type`` starts with, on either backend."""
    kind = SYMBOLS_FOR_GEOMETRY.get(geometry_type, "marker")
    color = "#808080"
    if kind == "line":
        return SingleSymbolRenderer(symbol=LineSymbol(color=color))
    if kind == "fill":
        return SingleSymbolRenderer(symbol=FillSymbol(color=color))
    return SingleSymbolRenderer(symbol=MarkerSymbol(color=color))


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


def _table_entry(declaration: TableDeclaration) -> dict[str, object]:
    """The browse item and the vector shape one declared table answers."""
    return {
        "item": ConnectionItem(
            name=declaration.name,
            schema=declaration.schema,
            kind=declaration.kind,
            geometries=tuple(declaration.geometries),
        ),
        "fields": tuple(declaration.fields),
        "crs": declaration.crs,
    }


def _refuse_unopenable(kind: str) -> None:
    if kind == "schema":
        raise QgisSdkUnsupportedCapabilityError(
            "connections.open_layer",
            "a schema is browsed, not opened",
        )
    if kind == "raster":
        raise QgisSdkUnsupportedCapabilityError(
            "connections.open_layer",
            "a raster table is opened by its raster provider, not "
            "described as a vector layer",
        )


def _missing_table(connections, key, name, schema, item):
    schemas = connections._connections[key]["schemas"]
    if not schema and item in schemas:  # type: ignore[operator]
        raise QgisSdkUnsupportedCapabilityError(
            "connections.open_layer",
            "a schema is browsed, not opened",
        )
    raise QgisSdkConnectionItemNotFoundError(name, schema or "", item)


class FakeConnections:
    """A ``Connections`` backend over connections declared in the test.

    The fake stores descriptions and answers from them, and its one piece of
    real behaviour is the same the native adapter enforces: **nothing secret is
    stored or answered**. A declaration carries an authentication configuration
    *id*, never the material behind it, and :meth:`attach_auth_config` swaps the
    id the description answers - which is what "attaching" means at this
    boundary.

    A declaration also says what the fake will not pretend: ``valid=False``
    makes :meth:`test` answer the refusal (a message the test wrote, because
    the fake has no provider to refuse with) and ``accepts_auth=False`` makes
    attachment fail the way a file-based connection's does natively.
    """

    def __init__(self, layers: FakeLayers) -> None:
        self._layers = layers
        self._connections: dict[tuple[str, str], dict[str, object]] = {}
        self._tables: dict[tuple[str, str], list[dict[str, object]]] = {}
        self._auth: dict[str, AuthConfiguration] = {}
        self._opened = 0

    def declare_connection(self, declaration: ConnectionDeclaration) -> None:
        """Declare one registered connection and the schemas it browses to."""
        key = (declaration.provider, declaration.name)
        self._connections[key] = {
            "auth_config": declaration.auth_config,
            "schemas": tuple(declaration.schemas),
            "valid": declaration.valid,
            "message": declaration.message,
            "accepts_auth": declaration.accepts_auth,
        }
        self._tables.setdefault(key, [])

    def declare_table(self, declaration: TableDeclaration) -> None:
        """Declare one table or view inside a declared connection."""
        key = (declaration.provider, declaration.connection)
        if key not in self._connections:
            raise QgisSdkDeclarationError(
                f"connection {declaration.connection!r} of provider "
                f"{declaration.provider!r} is not declared before its tables"
            )
        self._tables[key].append(_table_entry(declaration))

    def declare_auth_configuration(self, name: str) -> str:
        """Declare one authentication configuration and answer its id.

        The id is the registry's to choose here exactly as it is natively
        (``QgsAuthManager`` assigns one), so a test keeps the id it is handed
        and never writes one it expects back.
        """
        auth_config = f"cfg{len(self._auth) + 1:04d}"
        self._auth[auth_config] = AuthConfiguration(id=auth_config, name=name)
        return auth_config

    def list_connections(self) -> tuple[ConnectionInfo, ...]:
        return tuple(self._describe(key) for key in self._connections)

    def connection(self, provider: str, name: str) -> ConnectionInfo:
        self._require(provider, name)
        return self._describe((provider, name))

    def browse(
        self, provider: str, name: str, schema: str | None = None
    ) -> tuple[ConnectionItem, ...]:
        key = self._require(provider, name)
        declared = self._connections[key]
        schemas: tuple[str, ...] = declared["schemas"]  # type: ignore[assignment]
        if not schema:
            if schemas:
                return tuple(
                    ConnectionItem(name=each, schema="", kind="schema")
                    for each in schemas
                )
            return tuple(entry["item"] for entry in self._tables[key])  # type: ignore[misc]
        if schema not in schemas:
            raise QgisSdkConnectionItemNotFoundError(name, schema, "")
        return tuple(
            entry["item"]  # type: ignore[misc]
            for entry in self._tables[key]
            if entry["item"].schema == schema  # type: ignore[union-attr]
        )

    def open_layer(
        self, provider: str, name: str, schema: str, item: str
    ) -> VectorLayerInfo:
        key = self._require(provider, name)
        for entry in self._tables[key]:
            declared: ConnectionItem = entry["item"]  # type: ignore[assignment]
            if declared.name != item or declared.schema != (schema or ""):
                continue
            _refuse_unopenable(declared.kind)
            self._opened += 1
            source = Path(f"fake-connection:{provider}:{name}:{schema or '-'}:{item}")
            fields: tuple[str, ...] = entry["fields"]  # type: ignore[assignment]
            self._layers.register(
                VectorLayerDeclaration(
                    source,
                    name=item,
                    geometry_type=(
                        declared.geometries[0] if declared.geometries else "none"
                    ),
                    field_names=fields,
                    crs=entry["crs"],
                )
            )
            return self._layers.open_vector(source)
        return _missing_table(self, key, name, schema, item)

    def test(self, provider: str, name: str) -> ConnectionTest:
        key = self._require(provider, name)
        declared = self._connections[key]
        if declared["valid"]:
            return ConnectionTest(valid=True)
        message = declared["message"] or "the declared connection does not answer"
        return ConnectionTest(valid=False, message=str(message))

    def auth_configurations(self) -> tuple[AuthConfiguration, ...]:
        return tuple(self._auth.values())

    def attach_auth_config(self, provider: str, name: str, auth_config: str) -> None:
        key = self._require(provider, name)
        if auth_config not in self._auth:
            raise QgisSdkAuthConfigNotFoundError(auth_config)
        declared = self._connections[key]
        if not declared["accepts_auth"]:
            raise QgisSdkUnsupportedCapabilityError(
                "auth.attach",
                f"connection {name!r} of provider {provider!r} authenticates "
                "without a configuration; there is none to attach",
            )
        declared["auth_config"] = auth_config

    def _require(self, provider: str, name: str) -> tuple[str, str]:
        key = (provider, name)
        if key not in self._connections:
            raise QgisSdkConnectionNotFoundError(provider, name)
        return key

    def _describe(self, key: tuple[str, str]) -> ConnectionInfo:
        declared = self._connections[key]
        return ConnectionInfo(
            name=key[1],
            provider=key[0],
            auth_config=declared["auth_config"],  # type: ignore[arg-type]
        )
