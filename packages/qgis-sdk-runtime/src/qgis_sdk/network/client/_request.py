"""Validating and resolving one call into the request a transport receives.

Every refusal is a :class:`QgisSdkRequestRejectedError` raised before any
transport is touched, so a mistake costs no socket and no host round trip.
One :class:`~qgis_sdk.services.network.RequestOptions` mapping carries the
per-call knobs and one :class:`~qgis_sdk.services.network.ConfigureOptions`
mapping carries a derived client's overrides (decision-81). Both mappings are
parsed into frozen records before any transport is touched, so defaults and
limit checks live in one place.
"""

from __future__ import annotations

import json as json_module
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import isfinite
from urllib.parse import urlencode, urlsplit, urlunsplit

from qgis_sdk.models import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT_SECONDS,
    Headers,
    NetworkRequest,
    QgisSdkRequestRejectedError,
    QgisSdkResponseTooLargeError,
    Response,
)
from qgis_sdk.services import Params
from qgis_sdk.services.network import ConfigureOptions, RequestOptions

__all__ = ["NetworkDefaults", "build_request"]

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


@dataclass(frozen=True, slots=True)
class _RequestValues:
    """One call's parsed options, with every omission spelled once."""

    params: Params | None = None
    json: object = None
    data: bytes | str | Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None
    timeout: float | None = None


@dataclass(frozen=True, slots=True)
class _ConfigureValues:
    """The overrides a derived client asked for, already checked."""

    base_url: str | None = None
    headers: Mapping[str, str] | None = None
    timeout: float | None = None
    auth_config: str | None = None
    max_redirects: int | None = None
    max_body_bytes: int | None = None


def _request_values(options: RequestOptions | None) -> _RequestValues:
    """Parse one call's mapping; an unknown key is a caller's mistake."""
    return _RequestValues(**(options or {}))


def configure_values(options: ConfigureOptions) -> _ConfigureValues:
    """Parse and refuse nonsense limits before a derived client is built."""
    values = _ConfigureValues(**options)
    if values.max_redirects is not None and values.max_redirects < 0:
        raise QgisSdkRequestRejectedError("max_redirects must not be negative")
    if values.max_body_bytes is not None and values.max_body_bytes < 1:
        raise QgisSdkRequestRejectedError("max_body_bytes must be at least 1")
    if values.timeout is not None and (
        not isfinite(values.timeout) or values.timeout <= 0
    ):
        raise QgisSdkRequestRejectedError(
            "timeout must be a positive number of seconds"
        )
    return values


def derive_defaults(
    current: NetworkDefaults, values: _ConfigureValues
) -> NetworkDefaults:
    """Layer the asked-for overrides over the current immutable defaults."""
    return replace(
        current,
        base_url=current.base_url if values.base_url is None else values.base_url,
        headers=current.headers.merge(values.headers),
        timeout_seconds=(
            current.timeout_seconds if values.timeout is None else values.timeout
        ),
        auth_config=(
            current.auth_config if values.auth_config is None else values.auth_config
        ),
        max_redirects=(
            current.max_redirects
            if values.max_redirects is None
            else values.max_redirects
        ),
        max_body_bytes=(
            current.max_body_bytes
            if values.max_body_bytes is None
            else values.max_body_bytes
        ),
    )


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


def _verb(method: str, url: str) -> str:
    verb = method.upper()
    if verb not in _METHODS:
        raise _reject(f"method {method!r} is not supported", verb, url)
    return verb


def _merged_headers(
    defaults: Headers, extra: Mapping[str, str] | None, implied_type: str | None
) -> Headers:
    merged = defaults.merge(extra)
    if implied_type is not None and "content-type" not in merged:
        merged = merged.merge({"Content-Type": implied_type})
    return merged


def _seconds(default: float, override: float | None, verb: str, url: str) -> float:
    seconds = default if override is None else override
    if not isfinite(seconds) or seconds <= 0:
        raise _reject("timeout must be a positive number of seconds", verb, url)
    return float(seconds)


def build_request(
    defaults: NetworkDefaults,
    method: str,
    url: str,
    options: RequestOptions | None = None,
) -> NetworkRequest:
    """Validate and resolve one call into the request a transport receives.

    Every refusal is a :class:`QgisSdkRequestRejectedError` raised before any
    transport is touched, so a mistake costs no socket and no host round trip.
    """
    values = _request_values(options)
    verb = _verb(method, url)
    resolved = _with_params(_resolve_url(url, defaults.base_url, verb), values.params)
    body, implied_type = _encode_body(values.json, values.data, verb, resolved)
    headers = _merged_headers(defaults.headers, values.headers, implied_type)
    seconds = _seconds(defaults.timeout_seconds, values.timeout, verb, resolved)
    return NetworkRequest(
        method=verb,
        url=resolved,
        headers=headers,
        body=body,
        timeout_seconds=seconds,
        max_redirects=defaults.max_redirects,
        max_body_bytes=defaults.max_body_bytes,
        auth_config=defaults.auth_config,
    )


def check_size(request: NetworkRequest, response: Response) -> Response:
    """Backstop the ceiling a transport should already have enforced."""
    if len(response.content) > request.max_body_bytes:
        raise QgisSdkResponseTooLargeError(
            request.max_body_bytes, method=request.method, url=response.url
        )
    return response
