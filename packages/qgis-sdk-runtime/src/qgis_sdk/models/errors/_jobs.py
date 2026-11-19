"""The remaining job-layer errors: forms, surfaces, the bridge and the network."""

from __future__ import annotations

from ._base import QgisSdkError


class QgisSdkFormError(QgisSdkError):
    """A declared action cannot be rendered, or the submitted values are refused.

    Raised by the QGIS-free form rules, so it carries no Qt objects and can be
    asserted without a host: rendering failures name the field that has no
    widget, and coercion failures name the field and the type it expected. The
    offending value is never echoed, because a form field can hold a path or a
    credential.
    """

    code = "invalid_form_values"


class QgisSdkUiError(QgisSdkError):
    """A surface or a view-scoped action call was refused, by name.

    Raised by the QGIS-free UI rules (``UiContext.actions``, the surface
    registry, the fakes) and by the Desktop host when it cannot honour a
    request - an action that still runs from the same view, a surface the
    plugin never registered, a typed action triggered from a bare binding.
    """

    code = "ui_refused"


class QgisSdkAppError(QgisSdkError):
    """The application host cannot start, run or stop the plugin as asked.

    Raised by the QGIS-free session (``qgis_sdk.app.run``): a second application
    in the same process, a quit with nothing running, a negative grace period, a
    backend that reports a host other than ``app`` - and by the Qt backend when
    ``QgsApplication`` already exists. The message always names the condition, so
    a launcher can show it without a stack trace.
    """

    code = "app_refused"


class QgisSdkBridgeError(QgisSdkError):
    """A bridge call was refused, or its value cannot cross the transport.

    The dispatcher turns this into an error reply rather than an exception, so a
    view always receives a call id it can match: a raise here would lose the
    correlation and leave the frontend waiting for a reply that never comes.
    """

    code = "bridge_error"


class QgisSdkBridgeProtocolError(QgisSdkBridgeError):
    """An envelope does not match the versioned bridge protocol."""

    code = "invalid_bridge_message"


class QgisSdkBridgeRefusalError(QgisSdkBridgeError):
    """An operation refused a call for a reason the view can act on.

    Unlike an ordinary failure, which the dispatcher reports as
    ``operation_failed``, a refusal keeps its own ``code`` on the wire: a view
    that is told ``stale_handle`` asks the user to pick the file again, one told
    ``grant_refused`` stops offering the action. The message names the handle
    or the rule, never the path or the secret behind it.
    """

    code = "grant_refused"


class QgisSdkInvalidRequestError(QgisSdkBridgeRefusalError):
    """A call asked for something the surface does not accept.

    A page asking for a page size above the ceiling, or a bbox that is not four
    numbers, hears ``invalid_payload`` and the bound it crossed, rather than a
    generic failure it cannot act on.
    """

    code = "invalid_payload"


class QgisSdkGrantRefusedError(QgisSdkBridgeRefusalError):
    """The view holds no grant that allows what it asked for."""

    code = "grant_refused"


class QgisSdkUnknownHandleError(QgisSdkBridgeRefusalError):
    """A handle is not one the host minted for this view.

    A handle minted for another view is reported exactly like one that never
    existed: the reply must not become an oracle for other views' handles.
    """

    code = "unknown_handle"


class QgisSdkStaleHandleError(QgisSdkBridgeRefusalError):
    """A handle this view did hold is no longer valid.

    It was minted for a runtime generation that was replaced, it expired, or
    the host revoked it. The view has to obtain a fresh one; nothing is resolved
    by matching names or paths.
    """

    code = "stale_handle"


class QgisSdkFeatureEditError(QgisSdkError):
    """A provider refused a write, and the buffer says what it said.

    ``commit`` reports this rather than claiming the write was rolled back: a
    provider that wrote some rows and then failed has left them written, and
    reversing them is a provider capability the SDK cannot assume.
    """


class QgisSdkNetworkError(QgisSdkError):
    """Base of the network failures a caller can tell apart by ``code``.

    Every subclass carries the request's ``method`` and ``url`` so a log line
    says what failed; the URL never contains credentials, because the client
    refuses user-info in URLs before a transport is touched.

    Args:
        message: What went wrong, without repeating the request.
        method: The HTTP method of the request that failed.
        url: The URL it was sent to, never with credentials.
    """

    code = "network_error"

    def __init__(self, message: str, *, method: str = "", url: str = "") -> None:
        self.method = method
        self.url = url
        prefix = f"{method} {url}: " if method and url else ""
        super().__init__(f"{prefix}{message}")


class QgisSdkRequestRejectedError(QgisSdkNetworkError):
    """The request was refused before it was sent: bad URL, options or body."""

    code = "request_rejected"


class QgisSdkRequestCancelledError(QgisSdkNetworkError):
    """The owner cancelled the request, or its scope closed, before it finished."""

    code = "request_cancelled"


class QgisSdkConnectionError(QgisSdkNetworkError):
    """The host could not be reached or the connection broke; often retryable."""

    code = "connection_failed"


class QgisSdkRequestTimeoutError(QgisSdkNetworkError):
    """No complete response within the request's timeout.

    Args:
        timeout_seconds: The limit that expired, in seconds.
        method: The HTTP method of the request that timed out.
        url: The URL it was sent to.
    """

    code = "request_timeout"

    def __init__(
        self, timeout_seconds: float, *, method: str = "", url: str = ""
    ) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"no response within {timeout_seconds:g} s", method=method, url=url
        )


class QgisSdkTlsError(QgisSdkNetworkError):
    """The TLS handshake failed under the QGIS certificate configuration."""

    code = "tls_failed"
