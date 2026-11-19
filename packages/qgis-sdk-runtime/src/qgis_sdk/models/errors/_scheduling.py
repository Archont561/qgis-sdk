"""Errors from the scheduler: a submission refused, a job that never ran.

A job is settled before its body reaches a worker or not at all, so these
answers arrive before any author code has run.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from ._base import QgisSdkError, QgisSdkValidationIssue


class QgisSdkContractValidationError(QgisSdkError):
    """A request or result did not satisfy its declared wire contract.

    Args:
        direction: Which side failed: ``request`` or ``result``.
        issues: Where the value broke its contract, one issue each.
    """

    code = "contract_validation_failed"

    def __init__(
        self,
        direction: Literal["request", "result"],
        issues: Iterable[QgisSdkValidationIssue],
    ) -> None:
        self.direction = direction
        self.issues = tuple(issues)
        super().__init__(f"{direction.title()} contract validation failed")

    def as_dict(self) -> dict[str, object]:
        """Return stable error metadata without raw input or validator internals."""
        return {
            "code": self.code,
            "direction": self.direction,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class QgisSdkJobCancelledError(QgisSdkError):
    """Cancellation reached a job at its next suspension point.

    The scheduler throws this into the coroutine so author ``finally`` blocks
    run; suppressing it lets the work continue, because cancellation is
    cooperative and never proof that the worker stopped.

    Args:
        job_id: The job that was cancelled.
    """

    code = "job_cancelled"

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"Job {job_id} was cancelled at its next suspension point")


class QgisSdkJobRejectedError(QgisSdkError):
    """A job submission was refused before any author code ran.

    ``problems`` name what was wrong with the submission - inputs of the wrong
    type, most often - without repeating the submitted values.

    Args:
        job_id: The declaration id the submission was made under.
        problems: What was wrong with it, one sentence each.
    """

    code = "job_rejected"

    def __init__(self, job_id: str, problems: Iterable[str]) -> None:
        self.job_id = job_id
        self.problems = tuple(problems)
        listed = "; ".join(self.problems)
        super().__init__(f"Job {job_id!r} was refused: {listed}")


class QgisSdkJobPrerequisiteError(QgisSdkError):
    """A job declared with ``ctx.jobs.after(...)`` never started.

    ``ctx.jobs.after(handle)`` orders a job behind work already submitted. The
    ordering is enforced before the body reaches a worker, so the dependent job
    fails with this error - naming the prerequisite and how it ended - instead
    of running against a result that does not exist.

    Args:
        job_id: The job that never started.
        prerequisite_id: The attempt it was ordered behind.
        prerequisite_status: How that prerequisite ended.
    """

    code = "job_prerequisite_failed"

    def __init__(
        self, job_id: str, prerequisite_id: str, prerequisite_status: object
    ) -> None:
        self.job_id = job_id
        self.prerequisite_id = prerequisite_id
        self.prerequisite_status = str(prerequisite_status)
        super().__init__(
            f"Job {job_id!r} waits for {prerequisite_id!r}, which ended "
            f"{self.prerequisite_status}; its body never ran"
        )


class QgisSdkJobNotSettledError(QgisSdkError):
    """A result was asked for before the job reached a terminal state.

    Args:
        job_id: The attempt whose result was asked for.
        status: The state it is still in.
    """

    code = "job_not_settled"

    def __init__(self, job_id: str, status: str) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(f"Job {job_id!r} is still {status}; it has no result yet")


class QgisSdkJobWaitRefusedError(QgisSdkError):
    """A blocking wait for a job was attempted on the GUI thread.

    Waiting there would freeze the thread that delivers the outcome. Subscribe
    with ``on_success``/``on_failure``/``on_cancelled`` or read the ``result``
    property after a terminal callback instead.

    Args:
        job_id: The attempt a caller tried to wait for.
    """

    code = "job_wait_refused"

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(
            f"Job {job_id!r}: a blocking wait is refused on the GUI thread; "
            "subscribe to the outcome instead"
        )


class QgisSdkSchedulingBlockedError(QgisSdkError):
    """The scheduler refused a submission or in-process replacement.

    Work that cannot reach a safe point is named as the blocker: replacing the
    runtime anyway would delete native resources under a running worker.

    Args:
        blockers: The work that cannot reach a safe point, named.
    """

    code = "scheduling_blocked"

    def __init__(self, blockers: Iterable[str]) -> None:
        self.blockers = tuple(blockers)
        listed = "; ".join(self.blockers)
        super().__init__(f"Scheduling is blocked: {listed}")
