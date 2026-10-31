"""Expected failures that callers can distinguish without importing QGIS."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


class QgisSdkError(Exception):
    """Base class for expected SDK errors; adapters may translate its code."""

    code = "sdk_error"


class QgisSdkScopeClosedError(QgisSdkError):
    """An operation attempted to use an already disposed owner scope."""

    code = "scope_closed"

    def __init__(self) -> None:
        super().__init__("This resource scope has been disposed")


class QgisSdkUnsupportedCapabilityError(QgisSdkError):
    """The selected runtime does not offer an explicitly requested capability.

    ``reason`` is set when the capability exists elsewhere in the same runtime
    but not *here* - a worker thread, for example, which must not touch the
    project the driving thread owns (decision-65). The message then says why
    instead of only that the host lacks the service.
    """

    code = "unsupported_capability"

    def __init__(self, capability: str, reason: str | None = None) -> None:
        self.capability = capability
        self.reason = reason
        message = f"Capability {capability!r} is unavailable in this runtime"
        if reason is not None:
            message = f"Capability {capability!r} is unavailable here: {reason}"
        super().__init__(message)


class QgisSdkOptionalDependencyError(QgisSdkError):
    """An explicitly selected adapter needs an administrator-provisioned package."""

    code = "optional_dependency_unavailable"

    def __init__(self, dependency: str, installation_hint: str) -> None:
        self.dependency = dependency
        self.installation_hint = installation_hint
        super().__init__(
            f"Optional dependency {dependency!r} is unavailable. {installation_hint}"
        )


class QgisSdkLayerNotFoundError(QgisSdkError):
    """No layer or dataset with this identifier exists in the runtime.

    The identifier is either a layer id or a dataset location, whichever the
    caller used, so the message never claims to know which kind was meant.
    """

    code = "layer_not_found"

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No layer {identifier!r} is available in this runtime")


class QgisSdkStyleIncompatibleError(QgisSdkError):
    """A packaged style cannot be applied to the target layer.

    Reasons are short, user-readable statements about the mismatch that was
    detected, never the rejected layer object.
    """

    code = "style_incompatible"

    def __init__(
        self,
        layer_id: str,
        style: str,
        reasons: Iterable[str],
    ) -> None:
        self.layer_id = layer_id
        self.style = style
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(
            f"Style {style!r} is incompatible with layer {layer_id!r}: {listed}"
        )


class QgisSdkStyleNotFoundError(QgisSdkError):
    """No reviewed style with this identifier is packaged with the SDK."""

    code = "style_not_found"

    def __init__(self, style: str) -> None:
        self.style = style
        super().__init__(f"No packaged style {style!r} is available")


class QgisSdkExportRefusedError(QgisSdkError):
    """An export cannot start as requested: the destination fails a precondition.

    Nothing has been written when this is raised. Every reason is reported at
    once - an unknown format, a missing directory and an existing file without
    ``overwrite`` are three separate statements, not three round trips.
    """

    code = "export_refused"

    def __init__(self, destination: str, reasons: Iterable[str]) -> None:
        self.destination = destination
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(f"Export to {destination!r} refused: {listed}")


class QgisSdkExportFailedError(QgisSdkError):
    """The writer failed after the export started; the partial file is gone.

    ``detail`` is the writer's own message. The destination was either never
    created or, with ``overwrite``, still holds its previous content: the new
    file is committed only after the writer finished.
    """

    code = "export_failed"

    def __init__(self, destination: str, detail: str) -> None:
        self.destination = destination
        self.detail = detail
        super().__init__(f"Export to {destination!r} failed: {detail}")


class QgisSdkPackagedResourceError(QgisSdkError):
    """A resource the package must ship is missing or unusable.

    This is a packaging defect, not a caller mistake: the style was requested by
    a known identifier and the layer was already found compatible.
    """

    code = "packaged_resource_unavailable"

    def __init__(self, style: str, detail: str) -> None:
        self.style = style
        self.detail = detail
        super().__init__(f"Packaged style {style!r} could not be used: {detail}")


@dataclass(frozen=True, slots=True)
class QgisSdkValidationIssue:
    """Safe, structured location and category for a rejected contract value."""

    path: tuple[str | int, ...]
    code: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue without including the rejected value."""
        return {"path": list(self.path), "code": self.code}


class QgisSdkContractValidationError(QgisSdkError):
    """A request or result did not satisfy its declared wire contract."""

    code = "contract_validation_failed"

    def __init__(
        self,
        direction: Literal["request", "result"],
        issues: Iterable[QgisSdkValidationIssue],
    ) -> None:
        self.direction = direction
        self.issues = tuple(issues)
        super().__init__(f"{direction.title()} contract validation failed")

    def as_dict(self) -> dict[str, object]:
        """Return stable error metadata without raw input or validator internals."""
        return {
            "code": self.code,
            "direction": self.direction,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class QgisSdkJobCancelledError(QgisSdkError):
    """Cancellation reached a job at its next suspension point.

    The scheduler throws this into the coroutine so author ``finally`` blocks
    run; suppressing it lets the work continue, because cancellation is
    cooperative and never proof that the worker stopped.
    """

    code = "job_cancelled"

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"Job {job_id} was cancelled at its next suspension point")


class QgisSdkJobRejectedError(QgisSdkError):
    """A job submission was refused before any author code ran.

    ``problems`` name what was wrong with the submission - inputs of the wrong
    type, most often - without repeating the submitted values.
    """

    code = "job_rejected"

    def __init__(self, job_id: str, problems: Iterable[str]) -> None:
        self.job_id = job_id
        self.problems = tuple(problems)
        listed = "; ".join(self.problems)
        super().__init__(f"Job {job_id!r} was refused: {listed}")


class QgisSdkJobPrerequisiteError(QgisSdkError):
    """A job declared with ``ctx.jobs.after(...)`` never started.

    ``ctx.jobs.after(handle)`` orders a job behind work already submitted. The
    ordering is enforced before the body reaches a worker, so the dependent job
    fails with this error - naming the prerequisite and how it ended - instead
    of running against a result that does not exist.
    """

    code = "job_prerequisite_failed"

    def __init__(
        self, job_id: str, prerequisite_id: str, prerequisite_status: object
    ) -> None:
        self.job_id = job_id
        self.prerequisite_id = prerequisite_id
        self.prerequisite_status = str(prerequisite_status)
        super().__init__(
            f"Job {job_id!r} waits for {prerequisite_id!r}, which ended "
            f"{self.prerequisite_status}; its body never ran"
        )


class QgisSdkJobNotSettledError(QgisSdkError):
    """A result was asked for before the job reached a terminal state."""

    code = "job_not_settled"

    def __init__(self, job_id: str, status: str) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(f"Job {job_id!r} is still {status}; it has no result yet")


class QgisSdkJobWaitRefusedError(QgisSdkError):
    """A blocking wait for a job was attempted on the GUI thread.

    Waiting there would freeze the thread that delivers the outcome. Subscribe
    with ``on_success``/``on_failure``/``on_cancelled`` or read the ``result``
    property after a terminal callback instead.
    """

    code = "job_wait_refused"

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(
            f"Job {job_id!r}: a blocking wait is refused on the GUI thread; "
            "subscribe to the outcome instead"
        )


class QgisSdkSchedulingBlockedError(QgisSdkError):
    """The scheduler refused a submission or in-process replacement.

    Work that cannot reach a safe point is named as the blocker: replacing the
    runtime anyway would delete native resources under a running worker.
    """

    code = "scheduling_blocked"

    def __init__(self, blockers: Iterable[str]) -> None:
        self.blockers = tuple(blockers)
        listed = "; ".join(self.blockers)
        super().__init__(f"Scheduling is blocked: {listed}")


class QgisSdkAlgorithmRejectedError(QgisSdkError):
    """An algorithm request was refused before it could touch any data.

    ``reasons`` are short statements about what made the request unsafe or
    ambiguous - an unspecified or geographic working CRS, units that are not
    metres, a distance that is not positive. They never include the rejected
    values themselves, so the error can be logged as-is.
    """

    code = "algorithm_rejected"

    def __init__(self, request: str, reasons: Iterable[str]) -> None:
        self.request = request
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(f"Algorithm request {request!r} was refused: {listed}")


class QgisSdkAlgorithmNotFoundError(QgisSdkError):
    """No algorithm with this id is registered on the host (or in the catalogue)."""

    code = "algorithm_not_found"

    def __init__(self, algorithm_id: str) -> None:
        self.algorithm_id = algorithm_id
        super().__init__(f"Algorithm {algorithm_id!r} is not registered")


class QgisSdkAlgorithmFailedError(QgisSdkError):
    """Processing ran the algorithm and it failed.

    ``detail`` describes the failure. SDK-owned staging is cleaned up on a
    best-effort basis; external provider side effects cannot be rolled back.
    """

    code = "algorithm_failed"

    def __init__(self, algorithm_id: str, detail: str) -> None:
        self.algorithm_id = algorithm_id
        self.detail = detail
        super().__init__(f"Algorithm {algorithm_id!r} failed: {detail}")


class QgisSdkAlgorithmCancelledError(QgisSdkError):
    """Cancellation was observed at an algorithm phase boundary.

    Cancellation is cooperative: this says the request was not run (or its
    result was not accepted), never that a native operation stopped mid-flight.
    """

    code = "algorithm_cancelled"

    def __init__(self, algorithm_id: str) -> None:
        self.algorithm_id = algorithm_id
        super().__init__(f"Algorithm {algorithm_id!r} was cancelled")


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


class QgisSdkNetworkError(QgisSdkError):
    """Base of the network failures a caller can tell apart by ``code``.

    Every subclass carries the request's ``method`` and ``url`` so a log line
    says what failed; the URL never contains credentials, because the client
    refuses user-info in URLs before a transport is touched.
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
    """No complete response within the request's timeout."""

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


class QgisSdkAuthenticationError(QgisSdkNetworkError):
    """The server or proxy demanded credentials the request could not supply."""

    code = "authentication_failed"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str = "",
        url: str = "",
    ) -> None:
        self.status_code = status_code
        super().__init__(message, method=method, url=url)


class QgisSdkRedirectError(QgisSdkNetworkError):
    """A redirect could not be followed: too many hops or an unsafe target."""

    code = "redirect_refused"


class QgisSdkResponseTooLargeError(QgisSdkNetworkError):
    """The body exceeds the buffered ceiling; it was not read into memory."""

    code = "response_too_large"

    def __init__(self, limit: int, *, method: str = "", url: str = "") -> None:
        self.limit = limit
        super().__init__(
            f"the response body exceeds the {limit} byte buffered limit",
            method=method,
            url=url,
        )


class QgisSdkHttpStatusError(QgisSdkNetworkError):
    """``raise_for_status`` found a 4xx or 5xx; the response stays attached."""

    code = "http_status"

    def __init__(self, status_code: int, reason: str, *, method: str, url: str) -> None:
        self.status_code = status_code
        self.reason = reason
        super().__init__(
            f"HTTP {status_code} {reason}".rstrip(), method=method, url=url
        )


class QgisSdkDecodeError(QgisSdkNetworkError):
    """The body is not the text or JSON the caller asked for."""

    code = "decode_failed"


class QgisSdkBlockingOnGuiThreadError(QgisSdkNetworkError):
    """A blocking request was attempted on the GUI thread, which would freeze it."""

    code = "blocking_on_gui_thread"

    def __init__(self, *, method: str = "", url: str = "") -> None:
        super().__init__(
            "blocking requests are refused on the GUI thread; await the"
            " coroutine form instead",
            method=method,
            url=url,
        )


class QgisSdkThreadSafetyWarning(UserWarning):
    """A GUI-bound capability was read from a thread that does not own it.

    A warning rather than an error, because raising would turn a plugin that
    happens to work into a failing one; a development session (``qgis-sdk
    dev``) escalates the same finding to
    :class:`QgisSdkUnsupportedCapabilityError` at the call site (decision-69).
    """


class QgisSdkServiceResponseError(QgisSdkNetworkError):
    """A typed service client received a well-formed reply it cannot interpret."""

    code = "service_response_invalid"
