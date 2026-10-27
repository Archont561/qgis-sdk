"""One execution capability: run a registered algorithm into new, owned outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    ProviderInfo,
    RunResult,
    TypedRun,
    VectorLayerInfo,
)


class Algorithms(Protocol):
    """Run any algorithm the host's Processing registry holds.

    Every guarantee here is one decision-19 makes about destructive
    workflows, now for the whole registry (decision-64):

    * ``run`` never edits an input. Destination parameters the caller leaves
      out are allocated under a run directory this service owns; vector
      destinations come back as layers this runtime owns, everything else on
      disk as a readable :class:`~qgis_sdk.models.FileRef`, numbers and
      strings as they are.
    * A failed run leaves no partial output behind. Implementations remove
      what the run wrote before raising ``QgisSdkAlgorithmFailedError``.
    * Outputs are separate: adding one to the project is the caller's
      decision and happens only after success.

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
    snapshot and ``run`` from outputs the test scripted; whether a working
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

    def execute(self, request: AlgorithmRequest) -> VectorLayerInfo:
        """Run ``request`` into a new output and return its layer description."""
        ...
