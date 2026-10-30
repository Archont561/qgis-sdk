"""``ServerContext``: what a QGIS Server hook is handed, and what it never sees.

The hook signature decision-52 fixes is ``def f(ctx: ServerContext, request:
ServerRequest, response: ServerResponse)``. The context carries the services the
request's project makes possible (``project``, ``layers``, ``log``) as
capabilities, exactly like the other contexts, so a host that cannot provide one
refuses it by name instead of handing over ``None``. ``QgsServerInterface`` is
never here: it is a Qt object that cannot leave the adapter, and a test cannot
build one (decision-52 implementation note).

There is no ``workers`` capability and no ``ui``, ``desktop`` or ``views``: a
request is served on the server's own thread with no event loop, so nothing that
would need one can be reached from a hook. ``ctx.host`` is ``Host.SERVER``.
"""

from __future__ import annotations

from typing import ClassVar

from qgis_sdk.core.contexts import Capability, _Context
from qgis_sdk.core.host import Host
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.services import Layers, Log, Project

from ._request import ServerRequest
from ._response import ServerResponse

__all__ = ["ServerContext"]


class ServerContext(_Context):
    """One request's context: the request, its response and the request project.

    Assembled once by the host for a single request and never reused; its scope
    closes when the response is sent, which is what makes a job submitted from a
    hook request-scoped (decision-52). ``project``, ``layers`` and ``log`` are
    capabilities: a host that serves a request without a project - a
    capabilities-only deployment, a test - refuses them by name rather than
    returning a half-built service.
    """

    __slots__ = (
        "_layers",
        "_log",
        "_project",
        "host",
        "request",
        "response",
        "scope",
    )

    _capability_names: ClassVar[tuple[str, ...]] = ("project", "layers", "log")

    scope: ResourceScope
    request: ServerRequest
    response: ServerResponse
    #: Always ``Host.SERVER``: a context states which host it belongs to
    #: (decision-52 point 4), it never infers one.
    host: Host
    project: Capability[Project] = Capability()
    layers: Capability[Layers] = Capability()
    log: Capability[Log] = Capability()

    def __init__(
        self,
        scope: ResourceScope,
        request: ServerRequest,
        response: ServerResponse,
        project: Project | None = None,
        layers: Layers | None = None,
        log: Log | None = None,
    ) -> None:
        self._assemble(
            scope=scope,
            request=request,
            response=response,
            host=Host.SERVER,
            _project=project,
            _layers=layers,
            _log=log,
        )
