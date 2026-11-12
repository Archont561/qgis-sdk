"""The ``NetworkTransport`` over QGIS's own network stack.

Every request goes through ``QgsNetworkAccessManager``, so the proxy, the
authentication database and the certificate trust a user configured in QGIS
apply without the plugin knowing about them; ``auth_config`` on a request is
applied by the QGIS authentication manager, and no credential ever passes
through here. A reply is turned into a buffered ``Response`` on the thread
that owns the reply, and the live ``QNetworkReply`` is never handed out.

Three behaviours are the transport's rather than Qt's, because the network
limits measurements showed Qt's defaults would break decision-4:

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

from urllib.parse import urlsplit

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import (
    QByteArray,
    QCoreApplication,
    QThread,
    QTimer,
    QUrl,
)
from qgis.PyQt.QtNetwork import (
    QNetworkReply,
    QNetworkRequest,
)

from qgis_sdk.models import (
    Headers,
    QgisSdkAuthenticationError,
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


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_follow_p1(_s):
    _s.current = _s.reply.url()
    _s.target = _s.current.resolved(_s.location)
    _s.target_url = _s.target.toString()
    if _s.self._hops >= _s.self._request.max_redirects:
        return CcReturn(
            QgisSdkRedirectError(
                f"more than {_s.self._request.max_redirects} redirects",
                method=_s.self._method,
                url=_s.target_url,
            )
        )


def cc_follow_p2(_s):
    if _s.target.scheme().lower() not in ("http", "https"):
        return CcReturn(
            QgisSdkRedirectError(
                f"redirect to scheme {_s.target.scheme()!r} refused",
                method=_s.self._method,
                url=_s.target_url,
            )
        )
    if _s.current.scheme().lower() == "https" and _s.target.scheme().lower() == "http":
        return CcReturn(
            QgisSdkRedirectError(
                "redirect from https to http refused",
                method=_s.self._method,
                url=_s.target_url,
            )
        )


def cc_follow_p3(_s):
    _s.allowed = _s.self._request.allowed_origins
    if _s.allowed is not None and origin_of(_s.target_url) not in _s.allowed:
        # The grant that constrained this request named the origins a hop
        # may reach; a redirect is how a granted origin would otherwise
        # hand the view's request to one that was not.
        return CcReturn(
            QgisSdkRedirectError(
                f"redirect to {origin_of(_s.target_url)!r} leaves the granted origins",
                method=_s.self._method,
                url=_s.target_url,
            )
        )
    return CcReturn(_follow_phase2(_s.current, _s.self, _s.status, _s.target_url))


def _issue_facts1(reply, self):
    reply.finished.connect(self._on_finished)
    timer = QTimer(reply)
    timer.setSingleShot(True)
    timer.timeout.connect(self._on_timeout)
    timer.start(int(self._request.timeout_seconds * 1000))
    self._timer = timer


def _classify_facts1(content, reason, reply, self, status):
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


def _follow_phase2(current, self, status, target_url):
    self._hops += 1
    if _origin(current.toString()) != _origin(target_url):
        # Credentials belong to the origin they were given for.
        self._headers = self._headers.without(*_CREDENTIAL_HEADERS)
        self._auth_config = None
    return _follow_phase1(self, status, target_url)


def _follow_phase1(self, status, target_url):
    if status == 303 or (status in (301, 302) and self._method == "POST"):
        self._method = "GET"
        self._body = None
        self._headers = self._headers.without("Content-Type", "Content-Length")
    self._issue(target_url)


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


def on_gui_thread() -> bool:
    application = QCoreApplication.instance()
    return application is not None and QThread.currentThread() is application.thread()


_FAILURE_CLASSES = (
    (_AUTH_ERRORS, QgisSdkAuthenticationError),
    (_TLS_ERRORS, QgisSdkTlsError),
    (_REDIRECT_ERRORS, QgisSdkRedirectError),
    ((_Error.OperationCanceledError,), QgisSdkRequestCancelledError),
)


class ExchangeMixin1:
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
        _issue_facts1(reply, self)

    def _send(self, qt_request: QNetworkRequest) -> QNetworkReply:
        method = self._method
        body = QByteArray(self._body) if self._body is not None else QByteArray()
        if self._body is None and method in ("GET", "DELETE"):
            accessor = (
                self._manager.get if method == "GET" else self._manager.deleteResource
            )
            return accessor(qt_request)
        name, takes_body = self._ACCESSORS.get(method, (None, False))
        if name is not None:
            return (
                getattr(self._manager, name)(qt_request, body)
                if takes_body
                else getattr(self._manager, name)(qt_request)
            )
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
        except Exception as error:  # noqa: BLE001 - see the note below
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

    def _refusal(self, reply: QNetworkReply) -> QgisSdkNetworkError | None:
        """The refusal that ends a request before its status is even read.

        The three are the local ones: the body the caller allowed itself, the
        deadline it set, and its own cancellation. None means the reply is
        worth classifying.
        """
        url = reply.url().toString()
        if self._too_large:
            return QgisSdkResponseTooLargeError(
                self._request.max_body_bytes, method=self._method, url=url
            )
        if self._timed_out:
            return QgisSdkRequestTimeoutError(
                self._request.timeout_seconds, method=self._method, url=url
            )
        if self._cancelled:
            return self._error(QgisSdkRequestCancelledError, "cancelled by its owner")
        return None

    def _classify(self, reply: QNetworkReply) -> Response | QgisSdkNetworkError | None:
        """Turn a finished reply into an outcome, or issue the next hop."""
        refusal = self._refusal(reply)
        if refusal is not None:
            return refusal
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
        return _classify_facts1(content, reason, reply, self, status)

    def _transport_failure(
        self, reply: QNetworkReply, error: QNetworkReply.NetworkError
    ) -> QgisSdkNetworkError:
        url = reply.url().toString()
        message = reply.errorString()
        if error in _TIMEOUT_ERRORS:
            return QgisSdkRequestTimeoutError(
                self._request.timeout_seconds, method=self._method, url=url
            )
        for known, failure_class in _FAILURE_CLASSES:
            if error in known:
                return failure_class(message, method=self._method, url=url)
        return QgisSdkConnectionError(message, method=self._method, url=url)
