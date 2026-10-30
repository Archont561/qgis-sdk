"""Handles: :class:`JobHandle` and the owner-bound :class:`BoundJob`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
)

from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import (
    object_schema,
)
from qgis_sdk.jobs._authoring import JobDescription, JobStatus
from qgis_sdk.jobs._subscriptions import JobSubscription
from qgis_sdk.models import (
    QgisSdkJobWaitRefusedError,
)

if TYPE_CHECKING:
    from qgis_sdk.jobs._attempt import _Attempt
    from qgis_sdk.jobs._service import JobService


# -- handles ------------------------------------------------------------------------


class JobHandle:
    """What ``delay`` returns: identity, state, cancellation, outcome, subscriptions.

    Everything on a handle is safe to call from the driving thread. ``cancel``
    and the read-only properties are safe from any thread; ``get`` is for any
    thread *but* the GUI thread.
    """

    __slots__ = ("_attempt",)

    def __init__(self, attempt: _Attempt) -> None:
        self._attempt = attempt

    # -- identity and state

    @property
    def id(self) -> str:
        """The logical job id: ``<declared id>#<submission number>``."""
        return self._attempt.id

    @property
    def attempt(self) -> int:
        """The attempt number; always ``1`` until an explicit retry policy exists."""
        return self._attempt.attempt

    @property
    def description(self) -> JobDescription:
        """The declaration this job was submitted from."""
        return self._attempt.description

    @property
    def status(self) -> JobStatus:
        """The current state; ``cancelled`` only once cancellation is acknowledged."""
        return self._attempt.status

    @property
    def cancel_requested(self) -> bool:
        """Whether anyone asked the job to stop, acknowledged or not."""
        return self._attempt.cancelled

    @property
    def owner_closed(self) -> bool:
        """Whether the owning scope was disposed, detaching every callback."""
        return self._attempt.owner_closed

    @property
    def progress(self) -> float | None:
        """The latest fraction reported, or ``None`` before any report."""
        return self._attempt.progress.latest

    @property
    def result(self) -> Any:
        """The typed result of a succeeded job.

        A failed job raises its own exception (the one ``error`` returns), a
        cancelled job raises ``QgisSdkJobCancelledError``, and a job that has
        not settled raises ``QgisSdkJobNotSettledError`` - the same reading
        :meth:`get` gives, without the wait.
        """
        return self._attempt.outcome()

    @property
    def error(self) -> BaseException | None:
        """The exception of a failed job, else ``None``."""
        return self._attempt.error

    # -- control

    def cancel(self) -> bool:
        """Request cancellation; return whether the job was still active.

        The request reaches the worker at once through the attempt's own
        signal, so a body polling ``ctx.cancellation`` sees it; the handle only
        settles when the worker reports.
        """
        active = self._attempt.job.cancel()
        self._attempt.request_cancel()
        return active

    def get(self, timeout: float | None = None) -> Any:
        """Block until the job settles and return its result.

        Refused on the GUI thread (``QgisSdkJobWaitRefusedError``) - that
        thread is the one delivering the outcome. Elsewhere it waits up to
        ``timeout`` seconds, raises ``QgisSdkJobNotSettledError`` when that
        runs out, re-raises a failure, and raises ``QgisSdkJobCancelledError``
        for a cancelled job.
        """
        attempt = self._attempt
        if attempt.runtime.gui_thread():
            raise QgisSdkJobWaitRefusedError(attempt.id)
        attempt.settled.wait(timeout)
        return attempt.outcome()

    # -- subscriptions

    def on_progress(
        self, callback: Callable[[float], None], *, owner: ResourceScope | None = None
    ) -> JobSubscription:
        """Hear the latest fraction once per tick it changed; replays the current one."""
        return self._attempt.subscribe("progress", callback, owner)

    def on_success(
        self, callback: Callable[[Any], None], *, owner: ResourceScope | None = None
    ) -> JobSubscription:
        """Hear the typed result exactly once."""
        return self._attempt.subscribe("success", callback, owner)

    def on_failure(
        self,
        callback: Callable[[BaseException], None],
        *,
        owner: ResourceScope | None = None,
    ) -> JobSubscription:
        """Hear the exception exactly once."""
        return self._attempt.subscribe("failure", callback, owner)

    def on_cancelled(
        self, callback: Callable[[], None], *, owner: ResourceScope | None = None
    ) -> JobSubscription:
        """Hear acknowledged cancellation exactly once."""
        return self._attempt.subscribe("cancelled", callback, owner)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, JobHandle) and other._attempt is self._attempt

    def __hash__(self) -> int:
        return hash(id(self._attempt))

    def __repr__(self) -> str:
        return f"JobHandle({self.id!r}, {self.status.value})"


#: How a ``JobHandle`` reads as an action *result* (decision-55: a surface's
#: ``ctx.actions.<id>()`` and a page both get the id and the status back; the
#: handle itself never crosses). ``-> JobHandle`` is a describable annotation.
JobHandle.__qgis_sdk_schema__ = object_schema(  # type: ignore[attr-defined]
    {
        "id": {"type": "string"},
        "status": {"type": "string", "enum": [status.value for status in JobStatus]},
    },
    ["id", "status"],
)


def _job_handle_wire(handle: JobHandle) -> dict[str, Any]:
    return {"id": handle.id, "status": handle.status.value}


JobHandle.__qgis_sdk_wire__ = _job_handle_wire  # type: ignore[attr-defined]


@dataclass(frozen=True, slots=True)
class BoundJob:
    """A job function bound to an owner; ``delay`` submits one attempt."""

    description: JobDescription
    function: Callable[..., Any]
    service: JobService = field(repr=False)

    def delay(self, **arguments: Any) -> JobHandle:
        """Submit one attempt with the inputs as keywords; no author code runs yet."""
        return self.service._submit(self, arguments)
