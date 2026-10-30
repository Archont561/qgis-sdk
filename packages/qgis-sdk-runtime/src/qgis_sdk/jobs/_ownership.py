"""Who is invoking the plugin handler that is running right now (decision-65 §3).

Ownership follows the *invocation*, never a mutable singleton. A view's
``ctx.actions.buffer(...)`` calls a handler the plugin instance owns, so the
handler itself holds the plugin's context; the view's authority has to travel
with the dispatch instead. It travels here: :data:`INVOKING_SCOPE` holds the
caller's scope for the duration of one synchronous handler call, and
:meth:`qgis_sdk.jobs.JobService.bind` reads it to submit view-owned work by
default, exactly as decision-21 promised.

Context variables are copied per task and per thread, so two views calling the
same action at the same time cannot read each other's owner, and a job body -
which runs on a worker - sees no owner at all: it is refused every job
capability by name. A host that wants request-scoped work (the server host,
TASK-80) sets the same variable around its own dispatch; nothing else has to
change for it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from qgis_sdk.core import ResourceScope

__all__ = ["INVOKING_SCOPE", "invoking", "invoking_scope"]

#: The scope of the caller whose handler is on the stack, or ``None``.
INVOKING_SCOPE: ContextVar[ResourceScope | None] = ContextVar(
    "qgis_sdk_invoking_scope", default=None
)


def invoking_scope() -> ResourceScope | None:
    """The scope of the dispatch in progress, or ``None`` outside one."""
    return INVOKING_SCOPE.get()


@contextmanager
def invoking(scope: ResourceScope | None) -> Iterator[None]:
    """Run one handler call on behalf of ``scope``; restore what was there before.

    Nested dispatches (an action that calls another action) restore the outer
    owner rather than clearing it, so the innermost caller always wins and the
    outer call still knows what it was.
    """
    token = INVOKING_SCOPE.set(scope)
    try:
        yield
    finally:
        INVOKING_SCOPE.reset(token)
