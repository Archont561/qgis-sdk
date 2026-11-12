"""The requests-like clients over an injected transport (decision-4).

:class:`NetworkClient` is what a host injects as ``ctx.network``. It validates
and resolves a request into a :class:`NetworkRequest`, hands it to the transport,
and suspends the calling job on a :class:`Handoff` until the transport delivers.
Nothing here blocks: the coroutine form yields to the step scheduler, and the
blocking form is a separate object the transport may refuse on the GUI thread.

Ownership follows the scope the client was built with: closing it cancels what
is in flight, and a request started after that is refused. Cancellation of the
awaiting job - thrown in at the suspension point by the scheduler - cancels the
transport request on the way out, so a cancelled job leaves no socket behind.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Unpack

from qgis_sdk.core import Handoff, ResourceScope
from qgis_sdk.models import (
    NetworkRequest,
    QgisSdkJobCancelledError,
    Response,
)
from qgis_sdk.services import NetworkTransport
from qgis_sdk.services.network import ConfigureOptions, RequestOptions

from ._request import (
    NetworkDefaults,
    build_request,
    check_size,
    configure_values,
    derive_defaults,
)

__all__ = ["BlockingNetworkClient", "NetworkClient"]


class BlockingNetworkClient:
    """The explicit blocking form of a :class:`NetworkClient`.

    It shares the client's transport, scope and defaults; the transport decides
    whether the calling thread may block, and refuses the GUI thread.
    """

    def __init__(
        self,
        transport: NetworkTransport,
        scope: ResourceScope,
        defaults: NetworkDefaults,
    ) -> None:
        self._transport = transport
        self._scope = scope
        self._defaults = defaults

    def get(self, url: str, **options: Unpack[RequestOptions]) -> Response:
        """Perform a GET on the calling thread."""
        return self.request("GET", url, **options)

    def post(self, url: str, **options: Unpack[RequestOptions]) -> Response:
        """Perform a POST on the calling thread."""
        return self.request("POST", url, **options)

    def request(
        self, method: str, url: str, **options: Unpack[RequestOptions]
    ) -> Response:
        """Perform any supported method on the calling thread."""
        request = build_request(self._defaults, method, url, options)
        self._scope.ensure_open()
        return check_size(request, self._transport.send_blocking(request))


class NetworkClient:
    """``ctx.network``: coroutine requests over one injected transport.

    Build one per owner scope. :meth:`configure` returns a derived client that
    shares the transport and scope but not the defaults, so a typed service
    client can carry its base URL and headers without touching the plugin's.
    """

    def __init__(
        self,
        transport: NetworkTransport,
        scope: ResourceScope,
        *,
        defaults: NetworkDefaults | None = None,
        _in_flight: dict[Handoff, Callable[[], None]] | None = None,
    ) -> None:
        self._transport = transport
        self._scope = scope
        self._defaults = defaults or NetworkDefaults()
        if _in_flight is None:
            _in_flight = {}
            scope.on_close(lambda: _cancel_all(_in_flight))
        self._in_flight = _in_flight

    @property
    def defaults(self) -> NetworkDefaults:
        """What this client sends with every request."""
        return self._defaults

    @property
    def transport(self) -> NetworkTransport:
        """The transport every request leaves through.

        Exposed so a host that builds the web-view surface from the plugin
        context (``HostServices.from_context``) can route ``network.fetch``
        through the same transport, grants and scope the Python client uses.
        """
        return self._transport

    @property
    def in_flight(self) -> int:
        """Requests started through this client (or a derivation) and not yet delivered."""
        return len(self._in_flight)

    @property
    def blocking(self) -> BlockingNetworkClient:
        """The same configuration, performed on the calling thread."""
        return BlockingNetworkClient(self._transport, self._scope, self._defaults)

    def configure(self, **options: Unpack[ConfigureOptions]) -> NetworkClient:
        """Derive a client with these defaults layered over the current ones."""
        derived = derive_defaults(self._defaults, configure_values(options))
        return NetworkClient(
            self._transport, self._scope, defaults=derived, _in_flight=self._in_flight
        )

    async def get(self, url: str, **options: Unpack[RequestOptions]) -> Response:
        """GET ``url``; suspends the job until the response is buffered."""
        return await self.request("GET", url, **options)

    async def post(self, url: str, **options: Unpack[RequestOptions]) -> Response:
        """POST to ``url`` with a ``json`` or ``data`` body."""
        return await self.request("POST", url, **options)

    async def request(
        self, method: str, url: str, **options: Unpack[RequestOptions]
    ) -> Response:
        """Send any supported method and await its buffered response."""
        request = build_request(self._defaults, method, url, options)
        self._scope.ensure_open()
        return await self._deliver(request)

    async def _deliver(self, request: NetworkRequest) -> Response:
        """Suspend on one handoff, forwarding cancellation to the transport."""
        cancels: list[Callable[[], None]] = []
        # A job cancelled while suspended here cannot resume until the transport
        # reports, so the handoff forwards the cancellation to the transport,
        # which answers with a cancelled outcome instead of leaving the job as a
        # replacement blocker (ADR-21).
        handoff = Handoff(on_cancel=lambda: [cancel() for cancel in cancels])
        cancel = self._transport.send(request, _deliver_outcome(handoff))
        cancels.append(cancel)
        self._in_flight[handoff] = cancel
        try:
            response = await handoff
        except QgisSdkJobCancelledError:
            # Cancellation delivered after author code suppressed an earlier one
            # still must not leave the transport request behind.
            cancel()
            raise
        finally:
            self._in_flight.pop(handoff, None)
        return check_size(request, response)


def _deliver_outcome(handoff: Handoff) -> Callable[[Response | Exception], None]:
    """Report exactly one transport outcome to the suspended job."""
    return lambda outcome: (
        handoff.fail(outcome)
        if isinstance(outcome, Exception)
        else handoff.resolve(outcome)
    )


def _cancel_all(in_flight: dict[Handoff, Callable[[], None]]) -> None:
    """Cancel every request the closing scope still owns."""
    for cancel in tuple(in_flight.values()):
        cancel()
    in_flight.clear()
