"""Scoped local jobs: one decorated function per job, bound to an owner, typed end to end.

decision-13 fixed the submission shape and decision-38 the authoring one:
``@job`` goes on a plain function ``def name(ctx: JobContext, ...) -> Result``
whose keyword parameters are typed the way an action's are, and the work is
submitted as ``ctx.jobs.bind(name).delay(**inputs)`` with the context injected
by the runtime at call time. decision-21 fixed what owns the work: a view by
default, a plugin only explicitly, with disposal detaching the view's callbacks
at once and *requesting* cancellation rather than pretending to have it. This
module is both, over the step scheduler, and it is QGIS-free: a host
drives :meth:`JobService.tick` from the event loop it already has, and that is
the only thread author callbacks ever run on.

Three rules carry the rest of the design and are worth stating once:

* **A request is not a state.** :meth:`JobHandle.cancel` sets
  :attr:`JobHandle.cancel_requested`; :attr:`JobHandle.status` becomes
  ``cancelled`` only when the job acknowledges it at a suspension point (or
  before it ever started). Work that completes anyway reports success.
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
from qgis_sdk.jobs._service import JobService
from qgis_sdk.jobs._subscriptions import JobFault, JobSubscription

__all__ = [
    "BoundJob",
    "JobDescription",
    "JobEvent",
    "JobFault",
    "JobHandle",
    "JobService",
    "JobStatus",
    "JobSubscription",
    "describe_job",
    "job",
]
