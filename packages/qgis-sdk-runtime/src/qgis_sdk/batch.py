"""Batch runs as jobs (TASK-94): several requests, one task, per-item seams.

A batch is the job form of running requests in order, the way
:mod:`qgis_sdk.layouts` is the job form of a render: :meth:`Algorithms.batch`
submits one job whose body runs every request with a progress fraction per
item and a cancellation check between items, so a host pumps one task bar for
ten runs instead of ten, and a user can stop the rest after the third report.

The body is built per submission because it is the only place the backend may
be reached from a worker (the layouts export precedent): the closure holds
the service, never a live request. The requests cross to the worker as
:class:`BatchItem` - plain values, the way a render's ``LayoutRequest`` does -
because a job body's inputs are the same JSON shapes a page sends and the
declaration subset carries no map type. A cancelled batch stops before the
next request and raises ``QgisSdkJobCancelledError``; the requests already run
stay run, each one a finished result rather than a partial one (decision-19,
decision-21).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from qgis_sdk.core import WorkerContext
from qgis_sdk.jobs import job
from qgis_sdk.models import (
    AlgorithmRun,
    QgisSdkAlgorithmRejectedError,
    QgisSdkJobCancelledError,
    RunResult,
    TypedRun,
)
from qgis_sdk.processing.runs import coerce_run
from qgis_sdk.services import Cancellation, Progress

__all__ = [
    "BATCH_JOB_ID",
    "BatchItem",
    "BatchParam",
    "BatchRequest",
    "BatchScalar",
    "BatchValue",
    "batch_body",
    "batch_items",
    "coerce_batch",
    "run_batch_items",
]

BATCH_JOB_ID = "algorithms.batch"
"""The job id one batch registers under, ``algorithms.batch``."""

#: One batch item: the three shapes :func:`qgis_sdk.processing.runs.coerce_run`
#: already accepts for a single run.
BatchRequest = AlgorithmRun | TypedRun | str

#: A parameter value as plain values: the JSON scalars, or an ordered array of
#: them (a multilayer's ids, a matrix row). This is the subset the declaration
#: language carries and the subset the wire sends.
BatchScalar = str | int | float | bool | None
BatchValue = BatchScalar | tuple[str | int | float | bool | None, ...]


@dataclass(frozen=True, slots=True)
class BatchParam:
    """One parameter of a batch item: its name and its plain value."""

    name: str
    value: BatchValue


@dataclass(frozen=True, slots=True)
class BatchItem:
    """One batch request as a job body receives it: plain values (decision-20).

    The params map crosses as ordered name/value pairs because a map is not a
    shape the declaration subset carries - the same reason a render's request
    names its destination as a resolved path rather than a ref.
    """

    algorithm: str
    params: tuple[BatchParam, ...]

    @classmethod
    def of(cls, run: AlgorithmRun) -> BatchItem:
        """One item from a validated run, params in order."""
        return cls(
            algorithm=run.algorithm,
            params=tuple(BatchParam(name, value) for name, value in run.params.items()),
        )

    def to_run(self) -> AlgorithmRun:
        """The run this item stands for, params by name again."""
        return AlgorithmRun(
            self.algorithm, {param.name: param.value for param in self.params}
        )


def coerce_batch(runs: Sequence[BatchRequest]) -> tuple[AlgorithmRun, ...]:
    """Every item in order, as plain runs; an empty batch is refused.

    Refused rather than tolerated because a batch of nothing reports no
    progress and answers no results - a caller that reached this either lost
    its requests or built them wrong, and both deserve the name.
    """
    if not runs:
        raise QgisSdkAlgorithmRejectedError(
            "batch", ["a batch runs at least one request"]
        )
    return tuple(coerce_run(item, None) for item in runs)


def batch_items(runs: Sequence[BatchRequest]) -> tuple[BatchItem, ...]:
    """Every item as the job body receives it, after the same checks."""
    return tuple(BatchItem.of(run) for run in coerce_batch(runs))


def run_batch_items(
    backend: Any,
    runs: Sequence[AlgorithmRun],
    *,
    progress: Progress,
    cancellation: Cancellation,
) -> tuple[RunResult, ...]:
    """Run every request in order, one item of progress at a time.

    The seam is per item: ``progress.report`` sees ``1/total``, ``2/total``
    and so on, and cancellation is read before each request, which is the
    granularity a run can honour (the atlas's per-page precedent).
    """
    total = len(runs)
    results: list[RunResult] = []
    for index, run in enumerate(runs):
        if cancellation.is_cancelled():
            raise QgisSdkJobCancelledError(0)
        results.append(backend.run(run))
        progress.report((index + 1) / total)
    return tuple(results)


def batch_body(backend: Any) -> Callable[..., Any]:
    """The ``@job`` body of one batch run, as a declaration."""

    @job(id=BATCH_JOB_ID, title="Run algorithm batch")
    def body(ctx: WorkerContext, runs: tuple[BatchItem, ...]) -> tuple[RunResult, ...]:
        return run_batch_items(
            backend,
            [item.to_run() for item in runs],
            progress=ctx.progress,
            cancellation=ctx.cancellation,
        )

    return body
