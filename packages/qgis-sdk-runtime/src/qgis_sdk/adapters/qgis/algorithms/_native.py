from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem

from qgis_sdk.batch import batch_body, batch_items
from qgis_sdk.jobs import JobHandle, JobService
from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    BufferRequest,
    CentroidRequest,
    FileRef,
    ProviderInfo,
    QgisSdkAlgorithmNotFoundError,
    QgisSdkAlgorithmRejectedError,
    RunResult,
    TypedRun,
    VectorLayerInfo,
)
from qgis_sdk.processing.runs import (
    coerce_run,
)

from ._publish import buffer, centroid
from ._wiring import (
    METRES_ONLY,
    AlgorithmWiring,
    RunRequest,
    load_model,
    model_run_request,
    processing,
    run_described,
)


class NativeAlgorithms:
    """Run registered operations through QGIS Processing.

    ``working_directory`` is where temporary outputs go. The caller may supply
    one (a test asserting what is left behind does) - in that case the directory
    is not removed on scope close, because the runtime does not own it.
    """

    def __init__(self, wiring: AlgorithmWiring) -> None:
        self._layers = wiring.layers
        self._scope = wiring.scope
        self._files = wiring.files
        self._owns_root = wiring.working_directory is None
        root = (
            Path(tempfile.mkdtemp(prefix="qgis-sdk-algorithms-"))
            if wiring.working_directory is None
            else Path(wiring.working_directory)
        )
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._runs = 0
        self._jobs = JobService(wiring.scope, workers=wiring.workers)
        wiring.scope.on_close(self._release)

    # -- the registry -------------------------------------------------------

    def providers(self) -> tuple[ProviderInfo, ...]:
        self._scope.ensure_open()
        return self._catalogue().providers

    def list(self, provider: str | None = None) -> tuple[AlgorithmInfo, ...]:
        self._scope.ensure_open()
        catalogue = self._catalogue()
        return (
            catalogue.algorithms
            if provider is None
            else catalogue.by_provider(provider)
        )

    def describe(self, algorithm_id: str) -> AlgorithmInfo:
        """Describe one algorithm straight from the live registry."""
        self._scope.ensure_open()
        processing()
        from .catalogue import algorithm_info

        algorithm = QgsApplication.processingRegistry().algorithmById(algorithm_id)
        if algorithm is None:
            raise QgisSdkAlgorithmNotFoundError(algorithm_id)
        return algorithm_info(algorithm, algorithm.provider().id())

    def _catalogue(self):
        """The registry read in full; cheap enough to read per call."""
        from .catalogue import read_catalogue

        return read_catalogue()

    # -- the generic run ----------------------------------------------------

    def run(
        self,
        request: AlgorithmRun | TypedRun | str,
        params: Mapping[str, object] | None = None,
    ) -> RunResult:
        """Run any registered algorithm into new outputs under a run directory."""
        self._scope.ensure_open()
        run = coerce_run(request, params)
        return run_described(
            self,
            RunRequest(
                info=self.describe(run.algorithm),
                params=run.params,
                target=run.algorithm,
                label=run.algorithm,
            ),
        )

    def run_model(
        self, model: FileRef, params: Mapping[str, object] | None = None
    ) -> RunResult:
        """Load one ``.model3`` model file and run it like a registered one.

        The model describes itself (its parameters and the destination-backed
        outputs ``updateDestinationParameters`` derives), so the run follows
        the same staging, validation and output conversion path as
        :meth:`run` and the outputs come back as the kinds the registry
        describes for that model.
        """
        self._scope.ensure_open()
        if not isinstance(model, FileRef):
            raise QgisSdkAlgorithmRejectedError(
                "run_model",
                ["a model is a FileRef the host minted, not a path (decision-20)"],
            )
        processing()
        loaded = load_model(self, model)
        return run_described(self, model_run_request(self, loaded, model, params))

    def batch(self, runs: Sequence[AlgorithmRun | TypedRun | str]) -> JobHandle:
        """Submit the batch as one job through this backend's job service."""
        self._scope.ensure_open()
        return self._jobs.bind(batch_body(self)).delay(runs=batch_items(runs))

    @property
    def jobs(self) -> JobService:
        """The job service ``batch`` submits through."""
        return self._jobs

    # -- the hand-written predecessors --------------------------------------

    def execute(self, request: AlgorithmRequest) -> VectorLayerInfo:
        """Run one request into a new output layer and describe that layer."""
        self._scope.ensure_open()
        framework = processing()
        self._runs += 1
        run_directory = self._root / f"run-{self._runs}"
        run_directory.mkdir()
        try:
            if isinstance(request, BufferRequest):
                output = buffer(self, framework, request, run_directory)
            elif isinstance(request, CentroidRequest):
                output = centroid(self, framework, request, run_directory)
            else:
                raise QgisSdkAlgorithmRejectedError(
                    "execute", [f"unsupported request {type(request).__name__}"]
                )
        except BaseException:
            # decision-19: an incomplete output is removed before the caller sees
            # the failure, so a caller never has to know this directory exists.
            shutil.rmtree(run_directory, ignore_errors=True)
            raise
        return self._layers.open_vector(output)

    def _resolve(self, ref: FileRef, operation: str) -> Path:
        if self._files is None:
            raise QgisSdkAlgorithmRejectedError(
                "run", ["this runtime has no files service to resolve a FileRef with"]
            )
        return self._files.resolve(ref, operation=operation)

    def _release(self) -> None:
        """Remove this runtime's temporary tree; a caller's directory stays."""
        if self._owns_root:
            shutil.rmtree(self._root, ignore_errors=True)


def plain(value: Any) -> object:
    """A scalar output as Python: QGIS hands numbers, strings and booleans
    over already; anything else is kept only by its text."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return str(value)


def require_metric_projected_crs(authid: str, request: str) -> None:
    """Refuse a working CRS a distance cannot honestly be measured in."""
    crs = QgsCoordinateReferenceSystem(authid)
    if not crs.isValid():
        raise QgisSdkAlgorithmRejectedError(
            request, [f"working_crs {authid!r} is not a known CRS"]
        )
    if crs.isGeographic():
        raise QgisSdkAlgorithmRejectedError(
            request,
            [
                f"working_crs {authid!r} is geographic; a distance there would be degrees"
            ],
        )
    if crs.mapUnits() != Qgis.DistanceUnit.Meters:
        raise QgisSdkAlgorithmRejectedError(
            request,
            [
                f"working_crs {authid!r} is not in {METRES_ONLY}; distance_metres would be wrong"
            ],
        )
