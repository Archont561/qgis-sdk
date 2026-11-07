"""One execution capability: run a registered algorithm into new, owned outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    FileRef,
    ProviderInfo,
    RunResult,
    TypedRun,
    VectorLayerInfo,
)


class JobHandle(Protocol):
    """What the batch job form answers, as far as this layer may know it.

    The same surface :class:`qgis_sdk.services.layouts.JobHandle` declares -
    the id, the status, the settled result and the cancel request - and the
    concrete ``qgis_sdk.jobs.JobHandle`` satisfies it structurally. Nothing
    here constructs one; only the backend's job service submits work.
    """

    @property
    def id(self) -> str:
        """The attempt's id, ``algorithms.batch#1`` and so on."""
        ...

    @property
    def status(self) -> Any:
        """The attempt's state: queued, running, succeeded, failed or cancelled."""
        ...

    @property
    def result(self) -> Any:
        """The settled job's typed result; raises for a failed or cancelled one."""
        ...

    def cancel(self) -> bool:
        """Ask the job to stop; answer whether it was still active."""
        ...


class Algorithms(Protocol):
    """Run any algorithm the host's Processing registry holds.

    Omitted destination parameters are allocated under an SDK-owned run
    directory. A single explicit destination may name a new local GeoJSON or
    GeoPackage vector file; existing files and unsupported destinations are
    refused. The native adapter stages and validates the named output before
    publishing it without overwrite. On failure it attempts to remove its own
    staging and run directories, never a pre-existing destination. If result
    conversion fails after publication, the published file may remain.

    Providers execute trusted code, not in a sandbox: arbitrary algorithms can
    modify inputs or write elsewhere, and the SDK cannot roll back those side
    effects. Keep source and destination paths stable during execution. Vector
    outputs are owned layers; other outputs on disk are readable
    :class:`~qgis_sdk.models.FileRef` objects where available. Adding a layer
    to the project is the caller's decision after success.

    ``describe`` and ``list`` read the registry's own description (the
    :class:`~qgis_sdk.models.Catalogue` shape), so an installed third-party
    provider is as visible as ``native``. A request is validated against
    that description before any data is read: an unknown algorithm raises
    ``QgisSdkAlgorithmNotFoundError``, an unacceptable parameter mapping
    ``QgisSdkAlgorithmRejectedError``, an unknown layer
    ``QgisSdkLayerNotFoundError``.

    ``execute`` is the hand-written predecessor for ``BufferRequest`` and
    ``CentroidRequest``; it keeps its chained-reprojection behaviour and
    stays until a documented minor retires it.

    The in-memory double answers ``list``/``describe`` from the shipped
    snapshot, ``run`` and ``run_model`` from outputs the test scripted and
    ``batch`` as a real job over the same scripted runs; whether a working
    CRS is projected is still the native backend's own check.
    """

    def providers(self) -> tuple[ProviderInfo, ...]:
        """Every registered provider."""
        ...

    def list(self, provider: str | None = None) -> tuple[AlgorithmInfo, ...]:
        """Every registered algorithm, or those of one provider."""
        ...

    def describe(self, algorithm_id: str) -> AlgorithmInfo:
        """The registry's description of one algorithm."""
        ...

    def run(
        self,
        request: AlgorithmRun | TypedRun | str,
        params: Mapping[str, object] | None = None,
    ) -> RunResult:
        """Run one algorithm into new outputs and describe what it produced.

        ``request`` is a generated request class instance, an
        :class:`~qgis_sdk.models.AlgorithmRun`, or an algorithm id with
        ``params`` (the ``processing.run`` shape).
        """
        ...

    def run_model(
        self, model: FileRef, params: Mapping[str, object] | None = None
    ) -> RunResult:
        """Run one ``.model3`` model file into new outputs.

        ``model`` is a ref the host minted for the model file (decision-20);
        ``params`` fills the model's own parameters by name. The outputs come
        back tagged with the kinds the registry describes: an owned
        :class:`~qgis_sdk.models.VectorLayerInfo` per vector output, a
        :class:`~qgis_sdk.models.FileRef` per file, folder or report, a
        scalar per number, string or boolean, and a tuple of layers per
        multiple-layers output - exactly what :meth:`run` answers for a
        registered algorithm.
        """
        ...

    def batch(self, runs: Sequence[AlgorithmRun | TypedRun | str]) -> JobHandle:
        """Run requests in order as one job, and answer its handle.

        The job form of :meth:`run`: one task with a progress fraction per
        item and a cancellation check between items, so a batch of three
        reports shows ``1/3``, ``2/3``, ``3/3`` and stops before the next
        request when cancelled. The settled handle's ``result`` is the tuple
        of :class:`~qgis_sdk.models.RunResult`, oldest first.
        """
        ...

    @property
    def jobs(self) -> Any:
        """The job service ``batch`` submits through.

        A host pumps it beside the plugin's own ``ctx.jobs`` and the layouts
        service's: the batch jobs are declared here rather than in the
        plugin's registry, so a plugin that declares no jobs of its own still
        gets one task per batch.
        """
        ...

    def execute(self, request: AlgorithmRequest) -> VectorLayerInfo:
        """Run ``request`` into a new output and return its layer description."""
        ...
