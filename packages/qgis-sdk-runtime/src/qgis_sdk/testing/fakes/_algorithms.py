from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from qgis_sdk.batch import batch_body, batch_items
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.jobs import JobHandle, JobService
from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    CanvasExtent,
    Catalogue,
    FileRef,
    LayerInfo,
    MeshLayerInfo,
    PointCloudLayerInfo,
    ProviderInfo,
    QgisSdkAlgorithmFailedError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkLayerNotFoundError,
    RunResult,
    TiledSceneLayerInfo,
    TypedRun,
    VectorLayerInfo,
    VectorTileLayerInfo,
)
from qgis_sdk.processing.runs import coerce_run

from ._declarations import (
    DeclaredOutput,
    FakeAlgorithmSetup,
    OtherLayerDeclaration,
    ScriptedModelOutputs,
    ScriptedOutputs,
    VectorLayerDeclaration,
    resolve_outputs,
    validate_run,
)

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService


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
        validate_run(self, info, run)
        self.runs.append(run)
        answer = self._next_answer(run)
        outputs = resolve_outputs(self, info, answer)
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
            from qgis_sdk.testing.files import FakeFiles

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


EMPTY_COLLECTION = '{"type": "FeatureCollection", "features": []}\n'
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
    missing = [name for name in fields if name not in detail]
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


def vector_dataset(declaration: VectorLayerDeclaration) -> dict[str, object]:
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


def other_dataset(declaration: OtherLayerDeclaration) -> dict[str, object]:
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


class OtherKindLayers:
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
