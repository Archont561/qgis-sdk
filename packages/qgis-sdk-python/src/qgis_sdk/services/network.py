"""The networking contracts: one injected client, one injectable transport.

``ctx.network`` is a :class:`Network` (decision-4). Its coroutine methods are
the UI-facing form - they suspend on the step scheduler and never block the
thread that drives it - and :attr:`Network.blocking` is the explicit blocking
form, which a transport refuses on the GUI thread rather than nesting an event
loop. Both forms share one :class:`NetworkTransport`, which is what a host
adapter implements over ``QgsNetworkAccessManager`` and what a test replaces
with a scripted fake. Live ``QNetworkReply`` objects never cross either line.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from qgis_sdk.models import NetworkRequest, Response

__all__ = [
    "BlockingNetwork",
    "Deliver",
    "Network",
    "NetworkTransport",
    "Params",
]

Params = Mapping[str, str | int | float | bool | None]
"""Query parameters; a ``None`` value is omitted."""

Deliver = Callable[[Response | Exception], None]
"""How a transport reports exactly one outcome for one started request."""


class NetworkTransport(Protocol):
    """Where requests meet the host: QGIS's network stack, or a scripted fake.

    A transport receives requests that are already validated and resolved. It
    owns timeouts, redirects (dropping credentials when the origin changes),
    the body ceiling and the classification of failures into
    ``QgisSdkNetworkError`` subclasses.
    """

    def send(self, request: NetworkRequest, deliver: Deliver) -> Callable[[], None]:
        """Start ``request``; ``deliver`` is called once, on the driving thread.

        Returns a callable that cancels the request; a cancelled request is
        delivered as ``QgisSdkRequestCancelledError`` or not at all.
        """
        ...

    def send_blocking(self, request: NetworkRequest) -> Response:
        """Perform ``request`` on the calling thread and return its response.

        Raises ``QgisSdkBlockingOnGuiThreadError`` when the calling thread is
        the one a GUI depends on.
        """
        ...


class BlockingNetwork(Protocol):
    """The explicit blocking form; only for threads that may wait."""

    def get(
        self,
        url: str,
        *,
        params: Params | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response: ...

    def post(
        self,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response: ...

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response: ...


class Network(Protocol):
    """``ctx.network``: coroutine requests over the host's network configuration.

    ``get``/``post``/``request`` return awaitables that resolve to a buffered
    :class:`Response`; ``await`` them inside scheduled author code. ``json`` and
    ``data`` are mutually exclusive bodies. :meth:`configure` derives a client
    with other defaults and never mutates this one.
    """

    def get(
        self,
        url: str,
        *,
        params: Params | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Awaitable[Response]: ...

    def post(
        self,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Awaitable[Response]: ...

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Awaitable[Response]: ...

    def configure(
        self,
        *,
        base_url: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        auth_config: str | None = None,
        max_redirects: int | None = None,
        max_body_bytes: int | None = None,
    ) -> Network: ...

    @property
    def blocking(self) -> BlockingNetwork:
        """The same configuration, performed on the calling thread."""
        ...
