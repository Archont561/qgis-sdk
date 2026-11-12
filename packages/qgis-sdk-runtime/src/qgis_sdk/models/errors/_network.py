from ._jobs import QgisSdkNetworkError


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
