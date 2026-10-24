"""The ``NetworkTransport`` over QGIS's own network stack.

Every request goes through ``QgsNetworkAccessManager``, so the proxy, the
authentication database and the certificate trust a user configured in QGIS
apply without the plugin knowing about them; ``auth_config`` on a request is
applied by the QGIS authentication manager, and no credential ever passes
through here. A reply is turned into a buffered ``Response`` on the thread
that owns the reply, and the live ``QNetworkReply`` is never handed out.

Three behaviours are the transport's rather than Qt's, because the TASK-5
measurements showed Qt's defaults would break decision-4:

- **Redirects are followed here**, one request per hop, and ``Authorization``,
  ``Cookie`` and the auth configuration are dropped when the origin changes.
  The manager was measured forwarding both headers to another origin.
- **Timeouts are a timer per request**, so a timeout is reported as a timeout
  and never confused with a cancellation.
- **The body ceiling is enforced while downloading**: a reply that announces or
  delivers more than ``max_body_bytes`` is aborted, not buffered and then
  refused.

The blocking form runs the same exchange under a local event loop on the
calling thread and refuses the GUI thread outright.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from PyQt6.QtCore import (
    QByteArray,
    QCoreApplication,
    QEventLoop,
    QObject,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.core import QgsApplication, QgsNetworkAccessManager

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    Headers,
    NetworkRequest,
    QgisSdkAuthenticationError,
    QgisSdkBlockingOnGuiThreadError,
    QgisSdkConnectionError,
    QgisSdkNetworkError,
    QgisSdkRedirectError,
    QgisSdkRequestCancelledError,
    QgisSdkRequestTimeoutError,
    QgisSdkResponseTooLargeError,
    QgisSdkTlsError,
    Response,
)
from qgis_sdk.network.grants import origin_of
from qgis_sdk.services import Deliver

__all__ = ["NativeNetworkTransport"]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CREDENTIAL_HEADERS = ("Authorization", "Cookie", "Proxy-Authorization")

_Error = QNetworkReply.NetworkError
_TIMEOUT_ERRORS = frozenset({_Error.TimeoutError, _Error.ProxyTimeoutError})
_TLS_ERRORS = frozenset({_Error.SslHandshakeFailedError})
_AUTH_ERRORS = frozenset(
    {_Error.AuthenticationRequiredError, _Error.ProxyAuthenticationRequiredError}
)
_REDIRECT_ERRORS = frozenset(
    {_Error.TooManyRedirectsError, _Error.InsecureRedirectError}
)


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    return (parts.scheme.lower(), (parts.hostname or "").lower(), parts.port)


def _text(value: object) -> str:
    """PyQt hands header values back as ``str``, ``bytes`` or ``QByteArray``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return bytes(value).decode("latin-1")  # type: ignore[call-overload]


def _on_gui_thread() -> bool:
    application = QCoreApplication.instance()
    return application is not None and QThread.currentThread() is application.thread()


class _Exchange(QObject):
    """One request from first hop to delivered outcome.

    A ``QObject`` so that it has a thread: every reply it owns lives on the
    thread that started it, and a cancellation coming from another thread (a
    scope closing on the GUI thread while a blocking request runs on a worker)
    is queued to that thread instead of touching the reply directly.
    """

    _cancel_requested = pyqtSignal()

    def __init__(
        self,
        manager: QNetworkAccessManager,
        request: NetworkRequest,
        deliver: Deliver,
        on_done: Callable[[_Exchange], None],
    ) -> None:
        super().__init__()
        self._manager = manager
        self._request = request
        self._deliver = deliver
        self._on_done = on_done
        self._reply: QNetworkReply | None = None
        self._timer: QTimer | None = None
        self._hops = 0
        self._delivered = False
        self._cancelled = False
        self._timed_out = False
        self._too_large = False
        self._headers = request.headers
        self._auth_config = request.auth_config
        self._method = request.method
        self._body = request.body
        self._cancel_requested.connect(self._cancel_now)

    # -- driving -------------------------------------------------------------------

    def start(self) -> None:
        self._issue(self._request.url)

    def cancel(self) -> None:
        """Abort the current hop on its own thread; the finished handler delivers."""
        if self._delivered or self._cancelled:
            return
        self._cancelled = True
        if QThread.currentThread() is self.thread():
            self._cancel_now()
        else:
            self._cancel_requested.emit()

    def _cancel_now(self) -> None:
        if self._delivered:
            return
        if self._reply is not None:
            self._reply.abort()
        else:
            self._settle(
                self._error(QgisSdkRequestCancelledError, "cancelled by its owner")
            )

    def _issue(self, url: str) -> None:
        qt_request = QNetworkRequest(QUrl(url))
        qt_request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        for name, value in self._headers.items():
            qt_request.setRawHeader(name.encode("latin-1"), value.encode("latin-1"))
        if self._auth_config:
            applied = QgsApplication.authManager().updateNetworkRequest(
                qt_request, self._auth_config
            )
            # PyQt returns ``(ok, request)`` for the by-reference argument.
            if isinstance(applied, tuple):
                applied, qt_request = applied
            if not applied:
                self._settle(
                    self._error(
                        QgisSdkAuthenticationError,
                        f"QGIS authentication configuration {self._auth_config!r}"
                        " could not be applied",
                    )
                )
                return
        reply = self._send(qt_request)
        self._reply = reply
        reply.downloadProgress.connect(self._on_progress)
        reply.finished.connect(self._on_finished)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_timeout)
        timer.start(int(self._request.timeout_seconds * 1000))
        self._timer = timer

    def _send(self, qt_request: QNetworkRequest) -> QNetworkReply:
        method = self._method
        body = QByteArray(self._body) if self._body is not None else QByteArray()
        if method == "GET" and self._body is None:
            return self._manager.get(qt_request)
        if method == "HEAD":
            return self._manager.head(qt_request)
        if method == "POST":
            return self._manager.post(qt_request, body)
        if method == "PUT":
            return self._manager.put(qt_request, body)
        if method == "DELETE" and self._body is None:
            return self._manager.deleteResource(qt_request)
        return self._manager.sendCustomRequest(qt_request, method.encode("ascii"), body)

    # -- signals -------------------------------------------------------------------

    def _on_timeout(self) -> None:
        if self._reply is None or self._delivered:
            return
        self._timed_out = True
        self._reply.abort()

    def _on_progress(self, received: int, total: int) -> None:
        limit = self._request.max_body_bytes
        if self._reply is not None and (received > limit or total > limit):
            self._too_large = True
            self._reply.abort()

    def _on_finished(self) -> None:
        reply = self._reply
        if reply is None or self._delivered:
            return
        if self._timer is not None:
            self._timer.stop()
        self._reply = None
        try:
            outcome = self._classify(reply)
        except Exception as error:  # noqa: BLE001 - a Qt slot must not raise
            # An exception escaping a slot takes the whole host down under
            # PyQt6, so a surprise here becomes a delivered network error.
            outcome = QgisSdkNetworkError(
                f"reply handling failed: {error!r}",
                method=self._method,
                url=reply.url().toString(),
            )
        finally:
            reply.deleteLater()
        if outcome is None:
            return
        self._settle(outcome)

    # -- outcome -------------------------------------------------------------------

    def _classify(self, reply: QNetworkReply) -> Response | QgisSdkNetworkError | None:
        """Turn a finished reply into an outcome, or issue the next hop."""
        if self._too_large:
            return QgisSdkResponseTooLargeError(
                self._request.max_body_bytes,
                method=self._method,
                url=reply.url().toString(),
            )
        if self._timed_out:
            return QgisSdkRequestTimeoutError(
                self._request.timeout_seconds,
                method=self._method,
                url=reply.url().toString(),
            )
        if self._cancelled:
            return self._error(QgisSdkRequestCancelledError, "cancelled by its owner")
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is None:
            return self._transport_failure(reply, reply.error())
        # A status is a response, 401 and 407 included: the caller decides with
        # ``raise_for_status``; ``QgisSdkAuthenticationError`` is for QGIS being
        # unable to apply a configuration or a proxy challenge with no answer.
        if status in _REDIRECT_STATUSES:
            location = _text(reply.rawHeader(b"Location"))
            if location:
                return self._follow(reply, int(status), QUrl(location))
        content = bytes(reply.readAll())
        if len(content) > self._request.max_body_bytes:
            return QgisSdkResponseTooLargeError(
                self._request.max_body_bytes,
                method=self._method,
                url=reply.url().toString(),
            )
        reason = reply.attribute(QNetworkRequest.Attribute.HttpReasonPhraseAttribute)
        return Response(
            url=reply.url().toString(),
            status_code=int(status),
            reason=_text(reason),
            headers=Headers(
                (_text(name), _text(value)) for name, value in reply.rawHeaderPairs()
            ),
            content=content,
            method=self._method,
        )

    def _transport_failure(
        self, reply: QNetworkReply, error: QNetworkReply.NetworkError
    ) -> QgisSdkNetworkError:
        url = reply.url().toString()
        message = reply.errorString()
        if error in _TIMEOUT_ERRORS:
            return QgisSdkRequestTimeoutError(
                self._request.timeout_seconds, method=self._method, url=url
            )
        if error in _AUTH_ERRORS:
            return QgisSdkAuthenticationError(message, method=self._method, url=url)
        if error in _TLS_ERRORS:
            return QgisSdkTlsError(message, method=self._method, url=url)
        if error in _REDIRECT_ERRORS:
            return QgisSdkRedirectError(message, method=self._method, url=url)
        if error == _Error.OperationCanceledError:
            return QgisSdkRequestCancelledError(message, method=self._method, url=url)
        return QgisSdkConnectionError(message, method=self._method, url=url)

    def _follow(
        self, reply: QNetworkReply, status: int, location: QUrl
    ) -> QgisSdkNetworkError | None:
        current = reply.url()
        target = current.resolved(location)
        target_url = target.toString()
        if self._hops >= self._request.max_redirects:
            return QgisSdkRedirectError(
                f"more than {self._request.max_redirects} redirects",
                method=self._method,
                url=target_url,
            )
        if target.scheme().lower() not in ("http", "https"):
            return QgisSdkRedirectError(
                f"redirect to scheme {target.scheme()!r} refused",
                method=self._method,
                url=target_url,
            )
        if current.scheme().lower() == "https" and target.scheme().lower() == "http":
            return QgisSdkRedirectError(
                "redirect from https to http refused",
                method=self._method,
                url=target_url,
            )
        allowed = self._request.allowed_origins
        if allowed is not None and origin_of(target_url) not in allowed:
            # The grant that constrained this request named the origins a hop
            # may reach; a redirect is how a granted origin would otherwise
            # hand the view's request to one that was not.
            return QgisSdkRedirectError(
                f"redirect to {origin_of(target_url)!r} leaves the granted origins",
                method=self._method,
                url=target_url,
            )
        self._hops += 1
        if _origin(current.toString()) != _origin(target_url):
            # Credentials belong to the origin they were given for.
            self._headers = self._headers.without(*_CREDENTIAL_HEADERS)
            self._auth_config = None
        if status == 303 or (status in (301, 302) and self._method == "POST"):
            self._method = "GET"
            self._body = None
            self._headers = self._headers.without("Content-Type", "Content-Length")
        self._issue(target_url)
        return None

    def _error(
        self, kind: type[QgisSdkNetworkError], message: str
    ) -> QgisSdkNetworkError:
        return kind(message, method=self._method, url=self._request.url)

    def _settle(self, outcome: Response | QgisSdkNetworkError) -> None:
        if self._delivered:
            return
        self._delivered = True
        self._on_done(self)
        self._deliver(outcome)


class NativeNetworkTransport:
    """``NetworkTransport`` over ``QgsNetworkAccessManager``.

    One per owner scope: closing the scope aborts whatever is in flight. The
    manager defaults to the QGIS instance of the calling thread, which is how
    proxy, auth and certificate settings are inherited; pass one explicitly only
    in tests.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        manager: QNetworkAccessManager | None = None,
    ) -> None:
        self._scope = scope
        self._manager = manager
        self._active: set[_Exchange] = set()
        scope.on_close(self._abort_all)

    @property
    def in_flight(self) -> int:
        """Exchanges started and not yet delivered."""
        return len(self._active)

    def send(self, request: NetworkRequest, deliver: Deliver) -> Callable[[], None]:
        """Start the request on this thread's manager; deliver on this thread."""
        exchange = _Exchange(
            self._manager_for_thread(), request, deliver, self._active.discard
        )
        self._active.add(exchange)
        exchange.start()
        return exchange.cancel

    def send_blocking(self, request: NetworkRequest) -> Response:
        """Run the exchange under a local event loop; never on the GUI thread."""
        if _on_gui_thread():
            raise QgisSdkBlockingOnGuiThreadError(
                method=request.method, url=request.url
            )
        loop = QEventLoop()
        outcomes: list[Response | Exception] = []

        def deliver(outcome: Response | Exception) -> None:
            outcomes.append(outcome)
            loop.quit()

        self.send(request, deliver)
        if not outcomes:
            loop.exec()
        outcome = outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _manager_for_thread(self) -> QNetworkAccessManager:
        return (
            self._manager
            if self._manager is not None
            else QgsNetworkAccessManager.instance()
        )

    def _abort_all(self) -> None:
        for exchange in tuple(self._active):
            exchange.cancel()
