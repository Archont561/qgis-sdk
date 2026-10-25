"""A scripted ``NetworkTransport`` for tests that must never touch a network.

The fake is injected per client, exactly where ``NativeNetworkTransport`` would
be, so the client, the typed service clients and the scheduler run unchanged
(decision-4, decision-23). A test scripts what the host answers - a response,
a classified failure, or nothing until the test says so - and the fake records
every request it was asked to send. A request no expectation covers raises
:class:`QgisSdkNetworkFakeError` at once rather than inventing a reply.

What this proves is bounded: a green test says the caller handles what a host
*could* return; QGIS proxy, authentication and certificate behaviour is proven
only by the native transport's own integration tests.
"""

from __future__ import annotations

import json as json_module
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from qgis_sdk.models import (
    Headers,
    NetworkRequest,
    QgisSdkBlockingOnGuiThreadError,
    QgisSdkError,
    QgisSdkRedirectError,
    QgisSdkRequestCancelledError,
    Response,
)
from qgis_sdk.network.grants import origin_of
from qgis_sdk.services import Deliver

__all__ = ["FakeNetworkTransport", "PendingRequest", "QgisSdkNetworkFakeError", "reply"]

Responder = Callable[[NetworkRequest], Response | Exception]


class QgisSdkNetworkFakeError(QgisSdkError):
    """The script and the code under test disagree: unexpected or unmet requests."""

    code = "network_fake"


def reply(
    status: int = 200,
    *,
    body: bytes | str = b"",
    json: object = None,
    headers: Mapping[str, str] | None = None,
    reason: str | None = None,
    url: str | None = None,
) -> Responder:
    """Script a response; ``url`` overrides the final URL, as after a redirect."""
    if json is not None:
        content = json_module.dumps(json).encode("utf-8")
        merged = Headers({"Content-Type": "application/json"}).merge(headers)
    else:
        content = body.encode("utf-8") if isinstance(body, str) else body
        merged = Headers(headers)
    phrase = reason if reason is not None else _REASONS.get(status, "")

    def respond(request: NetworkRequest) -> Response:
        return Response(
            url=url or request.url,
            status_code=status,
            reason=phrase,
            headers=merged,
            content=content,
            method=request.method,
        )

    return respond


_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


@dataclass(slots=True)
class _Expectation:
    method: str
    url: str
    responder: Responder
    hold: bool

    def matches(self, request: NetworkRequest) -> bool:
        return request.method == self.method and request.url == self.url


@dataclass(slots=True)
class PendingRequest:
    """A held request the test settles when it chooses."""

    request: NetworkRequest
    _deliver: Deliver = field(repr=False)
    _responder: Responder = field(repr=False)
    settled: bool = False
    """Whether an outcome - scripted, substituted or cancelled - was delivered."""
    cancelled: bool = False
    """Whether the outcome was a cancellation requested by the owner."""

    def deliver(self) -> None:
        """Deliver what the expectation scripted."""
        self._settle(self._responder(self.request))

    def deliver_with(self, outcome: Response | Exception) -> None:
        """Deliver something else instead, such as a late failure."""
        self._settle(outcome)

    def _settle(self, outcome: Response | Exception) -> None:
        if self.settled:
            raise QgisSdkNetworkFakeError("this request was already settled")
        self.settled = True
        self._deliver(_within_grant(self.request, outcome))


def _within_grant(
    request: NetworkRequest, outcome: Response | Exception
) -> Response | Exception:
    """Apply the one grant rule a transport owns: a redirect stays inside.

    A scripted response whose final ``url`` sits on an origin the request's
    grant did not list is what a real redirect out of the grant would look like,
    so the fake refuses it exactly as the native transport does; a suite that
    scripts such a hop then fails for the right reason.
    """
    if request.allowed_origins is None or not isinstance(outcome, Response):
        return outcome
    if origin_of(outcome.url) in request.allowed_origins:
        return outcome
    return QgisSdkRedirectError(
        f"redirect to {origin_of(outcome.url) or outcome.url!r} leaves the "
        "granted origins",
        method=request.method,
        url=outcome.url,
    )


class FakeNetworkTransport:
    """Scripted transport: ``expect`` what will be asked, then ``assert_satisfied``.

    ``gui_thread`` scripts the thread check a real transport makes, so a test
    can prove the blocking form is refused where a GUI would freeze.
    """

    def __init__(self, *, gui_thread: bool = False) -> None:
        self.gui_thread = gui_thread
        self.requests: list[NetworkRequest] = []
        self.cancelled: list[NetworkRequest] = []
        self.pending: list[PendingRequest] = []
        self._expectations: list[_Expectation] = []
        self._unexpected: list[NetworkRequest] = []

    def expect(
        self,
        method: str,
        url: str,
        responder: Responder | Response | Exception | None = None,
        *,
        hold: bool = False,
    ) -> None:
        """Answer the next ``method url`` with ``responder``; ``hold`` waits for the test."""
        if responder is None:
            responder = reply()
        elif isinstance(responder, Response | Exception):
            fixed = responder

            def responder(_request: NetworkRequest) -> Response | Exception:
                return fixed

        self._expectations.append(_Expectation(method.upper(), url, responder, hold))

    @property
    def unmet(self) -> tuple[str, ...]:
        """Expectations no request consumed, as ``METHOD url``."""
        return tuple(f"{e.method} {e.url}" for e in self._expectations)

    @property
    def unexpected(self) -> tuple[NetworkRequest, ...]:
        """Requests no expectation covered; each was refused when it arrived."""
        return tuple(self._unexpected)

    def assert_satisfied(self) -> None:
        """Raise unless every expectation was met and nothing was left pending."""
        problems: list[str] = []
        if self._expectations:
            problems.append(f"unmet expectations: {', '.join(self.unmet)}")
        if self._unexpected:
            listed = ", ".join(f"{r.method} {r.url}" for r in self._unexpected)
            problems.append(f"unexpected requests: {listed}")
        open_requests = [p for p in self.pending if not p.settled]
        if open_requests:
            listed = ", ".join(
                f"{p.request.method} {p.request.url}" for p in open_requests
            )
            problems.append(f"requests still pending: {listed}")
        if problems:
            raise QgisSdkNetworkFakeError("; ".join(problems))

    # -- NetworkTransport -------------------------------------------------------

    def send(self, request: NetworkRequest, deliver: Deliver) -> Callable[[], None]:
        """Record the request and answer it now, or hold it for the test."""
        expectation = self._take(request)
        pending = PendingRequest(request, deliver, expectation.responder)
        self.pending.append(pending)

        def cancel() -> None:
            if pending.settled:
                return
            pending.cancelled = True
            pending.settled = True
            self.cancelled.append(request)
            deliver(
                QgisSdkRequestCancelledError(
                    "cancelled by its owner", method=request.method, url=request.url
                )
            )

        if not expectation.hold:
            pending.deliver()
        return cancel

    def send_blocking(self, request: NetworkRequest) -> Response:
        """Answer on the calling thread, or refuse it as a GUI thread would be."""
        if self.gui_thread:
            raise QgisSdkBlockingOnGuiThreadError(
                method=request.method, url=request.url
            )
        outcome = _within_grant(request, self._take(request).responder(request))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _take(self, request: NetworkRequest) -> _Expectation:
        self.requests.append(request)
        for index, expectation in enumerate(self._expectations):
            if expectation.matches(request):
                return self._expectations.pop(index)
        self._unexpected.append(request)
        raise QgisSdkNetworkFakeError(
            f"no expectation covers {request.method} {request.url}"
        )
