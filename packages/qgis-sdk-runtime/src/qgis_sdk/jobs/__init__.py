"""Scoped local jobs: one decorated function per job, bound to an owner, typed end to end.

decision-13 fixed the submission shape and decision-38 the authoring one:
``@job`` goes on a plain function ``def name(ctx: WorkerContext, ...) -> Result``
whose keyword parameters are typed the way an action's are. decision-65 fixed
how a plugin names the ones it exposes - ``jobs = {"add": add}`` or
``jobs = (add, count_features)`` - so the work is submitted as
``ctx.jobs.add.delay(**inputs)``: the name is the declaration, the inputs are
validated against the signature, and ``bind`` stays the host's tool rather than
the author's (0.9 migration). decision-21 fixed what owns the work: a view by
default, a plugin only explicitly, with disposal detaching the view's callbacks
at once and *requesting* cancellation rather than pretending to have it.
decision-65 fixed where the body runs: since 0.9.0 the whole function executes
on a worker through the ``Workers`` seam, and the driving thread only submits,
validates and delivers - so the injected context carries progress and
cancellation and nothing else, and a host without a worker backend refuses the
submission instead of running the body itself. This module is all of that, over
the step scheduler, and it is QGIS-free: a host drives
:meth:`JobService.tick` from the event loop it already has, and that is the only
thread author callbacks ever run on.

Three rules carry the rest of the design and are worth stating once:

* **A request is not a state.** :meth:`JobHandle.cancel` sets
  :attr:`JobHandle.cancel_requested`; :attr:`JobHandle.status` becomes
  ``cancelled`` only when the job acknowledges it (or before it ever started).
  A body acknowledges by stopping; a request that arrives before the worker
  reports settles the attempt at that report, so a body that runs to the end
  after being asked to stop still ends ``cancelled`` rather than publishing a
  result nobody is waiting for. Nothing interrupts a worker thread.
* **Callbacks are delivered on the tick, never from a worker.** Progress
  reported from a worker thread is coalesced to the latest fraction and
  delivered on the next tick; a terminal outcome is delivered exactly once.
  Subscribing after the fact replays the current state synchronously, once,
  and a terminal replay completes the subscription (decision-13).
* **Disposal beats delivery.** Closing the owner scope disposes every
  subscription it owns before anything else happens; a job the view no longer
  owns is asked to stop, but its attempt is not torn down under a worker that
  has not reported. Plugin unload is the one place everything is abandoned,
  and that is the scheduler's existing rule, not a new one.

No retries exist here, by decision. Resubmission is ``delay`` again, with a new
logical id; ``attempt`` is always ``1`` and is carried so a later, explicit
retry policy has somewhere to count.
"""

from __future__ import annotations

from qgis_sdk.jobs._authoring import (
    JobDescription,
    JobEvent,
    JobStatus,
    describe_job,
    job,
)
from qgis_sdk.jobs._handles import BoundJob, JobHandle
from qgis_sdk.jobs._jobs import Jobs, OrderedJobs
from qgis_sdk.jobs._ownership import INVOKING_SCOPE, invoking, invoking_scope
from qgis_sdk.jobs._registry import RESERVED_JOB_NAMES, JobRegistry
from qgis_sdk.jobs._service import JobService
from qgis_sdk.jobs._subscriptions import JobFault, JobSubscription

__all__ = [
    "INVOKING_SCOPE",
    "RESERVED_JOB_NAMES",
    "BoundJob",
    "JobDescription",
    "JobEvent",
    "JobFault",
    "JobHandle",
    "JobRegistry",
    "JobService",
    "JobStatus",
    "JobSubscription",
    "Jobs",
    "OrderedJobs",
    "describe_job",
    "invoking",
    "invoking_scope",
    "job",
]
