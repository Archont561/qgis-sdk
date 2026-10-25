"""The requests-like client over an injected transport (decision-4).

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

import json as json_module
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from math import isfinite
from urllib.parse import urlencode, urlsplit, urlunsplit

from qgis_sdk.core import Handoff, ResourceScope
from qgis_sdk.models import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT_SECONDS,
    Headers,
    NetworkRequest,
    QgisSdkJobCancelledError,
    QgisSdkRequestRejectedError,
    QgisSdkResponseTooLargeError,
    Response,
)
from qgis_sdk.services import NetworkTransport, Params

__all__ = ["BlockingNetworkClient", "NetworkClient", "NetworkDefaults", "build_request"]

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class NetworkDefaults:
    """What a derived client carries; immutable, so sharing one is safe."""

    base_url: str | None = None
    headers: Headers = field(default_factory=Headers)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    auth_config: str | None = None
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES


def _reject(message: str, method: str, url: str) -> QgisSdkRequestRejectedError:
    return QgisSdkRequestRejectedError(message, method=method, url=url)


def _resolve_url(url: str, base_url: str | None, method: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme:
        if base_url is None:
            raise _reject(
                "a relative URL needs a client configured with base_url", method, url
            )
        joined = f"{base_url.rstrip('/')}/{url.lstrip('/')}"
        parts = urlsplit(joined)
        url = joined
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise _reject(f"scheme {parts.scheme!r} is not http or https", method, url)
    if not parts.hostname:
        raise _reject("the URL has no host", method, url)
    if parts.username is not None or parts.password is not None:
        raise _reject(
            "credentials in URLs are refused; use a QGIS authentication configuration",
            method,
            f"{parts.scheme}://{parts.hostname}{parts.path}",
        )
    return url


def _with_params(url: str, params: Params | None) -> str:
    if not params:
        return url
    # Booleans render as ``true``/``false``: that is what JSON-era services
    # such as OGC API parse, and ``True`` is what Python would have sent.
    extra = urlencode(
        [
            (name, str(value).lower() if isinstance(value, bool) else value)
            for name, value in params.items()
            if value is not None
        ]
    )
    if not extra:
        return url
    parts = urlsplit(url)
    query = f"{parts.query}&{extra}" if parts.query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _encode_body(
    json: object,
    data: bytes | str | Mapping[str, str] | None,
    method: str,
    url: str,
) -> tuple[bytes | None, str | None]:
    """Return the body bytes and the content type they imply, if any."""
    if json is not None and data is not None:
        raise _reject("json and data are mutually exclusive bodies", method, url)
    if json is not None:
        try:
            encoded = json_module.dumps(json, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise _reject(
                f"json body is not serialisable: {error}", method, url
            ) from error
        return encoded.encode("utf-8"), "application/json"
    if data is None:
        return None, None
    if isinstance(data, bytes):
        return data, None
    if isinstance(data, str):
        return data.encode("utf-8"), "text/plain; charset=utf-8"
    return urlencode(list(data.items())).encode("ascii"), (
        "application/x-www-form-urlencoded"
    )


def build_request(
    defaults: NetworkDefaults,
    method: str,
    url: str,
    *,
    params: Params | None = None,
    json: object = None,
    data: bytes | str | Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> NetworkRequest:
    """Validate and resolve one call into the request a transport receives.

    Every refusal is a :class:`QgisSdkRequestRejectedError` raised before any
    transport is touched, so a mistake costs no socket and no host round trip.
    """
    verb = method.upper()
    if verb not in _METHODS:
        raise _reject(f"method {method!r} is not supported", verb, url)
    resolved = _with_params(_resolve_url(url, defaults.base_url, verb), params)
    body, implied_type = _encode_body(json, data, verb, resolved)
    merged = defaults.headers.merge(headers)
    if implied_type is not None and "content-type" not in merged:
        merged = merged.merge({"Content-Type": implied_type})
    seconds = defaults.timeout_seconds if timeout is None else timeout
    if not isfinite(seconds) or seconds <= 0:
        raise _reject("timeout must be a positive number of seconds", verb, resolved)
    return NetworkRequest(
        method=verb,
        url=resolved,
        headers=merged,
        body=body,
        timeout_seconds=float(seconds),
        max_redirects=defaults.max_redirects,
        max_body_bytes=defaults.max_body_bytes,
        auth_config=defaults.auth_config,
    )


def _check_size(request: NetworkRequest, response: Response) -> Response:
    """Backstop the ceiling a transport should already have enforced."""
    if len(response.content) > request.max_body_bytes:
        raise QgisSdkResponseTooLargeError(
            request.max_body_bytes, method=request.method, url=response.url
        )
    return response


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

    def get(
        self,
        url: str,
        *,
        params: Params | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        """Perform a GET on the calling thread."""
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def post(
        self,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        """Perform a POST on the calling thread."""
        return self.request(
            "POST",
            url,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )

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
    ) -> Response:
        """Perform any supported method on the calling thread."""
        request = build_request(
            self._defaults,
            method,
            url,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )
        self._scope.ensure_open()
        return _check_size(request, self._transport.send_blocking(request))


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

    def configure(
        self,
        *,
        base_url: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        auth_config: str | None = None,
        max_redirects: int | None = None,
        max_body_bytes: int | None = None,
    ) -> NetworkClient:
        """Derive a client with these defaults layered over the current ones."""
        if max_redirects is not None and max_redirects < 0:
            raise QgisSdkRequestRejectedError("max_redirects must not be negative")
        if max_body_bytes is not None and max_body_bytes < 1:
            raise QgisSdkRequestRejectedError("max_body_bytes must be at least 1")
        if timeout is not None and (not isfinite(timeout) or timeout <= 0):
            raise QgisSdkRequestRejectedError(
                "timeout must be a positive number of seconds"
            )
        current = self._defaults
        derived = replace(
            current,
            base_url=current.base_url if base_url is None else base_url,
            headers=current.headers.merge(headers),
            timeout_seconds=current.timeout_seconds if timeout is None else timeout,
            auth_config=current.auth_config if auth_config is None else auth_config,
            max_redirects=(
                current.max_redirects if max_redirects is None else max_redirects
            ),
            max_body_bytes=(
                current.max_body_bytes if max_body_bytes is None else max_body_bytes
            ),
        )
        return NetworkClient(
            self._transport, self._scope, defaults=derived, _in_flight=self._in_flight
        )

    async def get(
        self,
        url: str,
        *,
        params: Params | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        """GET ``url``; suspends the job until the response is buffered."""
        return await self.request(
            "GET", url, params=params, headers=headers, timeout=timeout
        )

    async def post(
        self,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        """POST to ``url`` with a ``json`` or ``data`` body."""
        return await self.request(
            "POST",
            url,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Params | None = None,
        json: object = None,
        data: bytes | str | Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        """Send any supported method and await its buffered response."""
        request = build_request(
            self._defaults,
            method,
            url,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )
        self._scope.ensure_open()
        cancels: list[Callable[[], None]] = []
        # A job cancelled while suspended here cannot resume until the transport
        # reports, so the handoff forwards the cancellation to the transport,
        # which answers with a cancelled outcome instead of leaving the job as a
        # replacement blocker (ADR-21).
        handoff = Handoff(on_cancel=lambda: [cancel() for cancel in cancels])

        def deliver(outcome: Response | Exception) -> None:
            if isinstance(outcome, Exception):
                handoff.fail(outcome)
            else:
                handoff.resolve(outcome)

        cancel = self._transport.send(request, deliver)
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
        return _check_size(request, response)


def _cancel_all(in_flight: dict[Handoff, Callable[[], None]]) -> None:
    """Cancel every request the closing scope still owns."""
    for cancel in tuple(in_flight.values()):
        cancel()
    in_flight.clear()
