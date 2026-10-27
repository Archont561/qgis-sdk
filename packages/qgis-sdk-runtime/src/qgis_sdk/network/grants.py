"""Per-view network grants (decision-20).

A view never receives the network. It receives a :class:`NetworkGrant`: the
origins it may reach, the methods it may use, whether it may spend the host's
QGIS authentication, and ceilings the host chose. The grant turns a request into
the request a transport receives (:meth:`NetworkGrant.constrain`) or refuses it
with :class:`~qgis_sdk.models.QgisSdkGrantRefusedError`, which names the rule
and never the credential.

Redirects are the part a single check cannot cover: the transport follows them
hop by hop, so the constrained request carries ``allowed_origins`` and every
transport refuses a hop that leaves them. Private-network reach is not a
separate policy here: an origin is reachable when it is listed, and
``http://127.0.0.1:8080`` is as explicit as any other.

Everything in this module is importable without Qt.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from math import isfinite
from urllib.parse import urlsplit

from qgis_sdk.models import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT_SECONDS,
    NetworkRequest,
    QgisSdkError,
    QgisSdkGrantRefusedError,
)

GRANT_MAX_BODY_BYTES = 1024 * 1024
"""Default body ceiling for a granted request.

A bridge view consumes the body as one stream event, so the grant's default is
well under the transport's measured 16 MiB ceiling; a host that needs more
says so when it mints the grant, up to :data:`DEFAULT_MAX_BODY_BYTES`.
"""

GRANT_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class QgisSdkGrantError(QgisSdkError):
    """A grant is malformed; the host author wrote it, not the view."""

    code = "invalid_grant"


def origin_of(url: str) -> str | None:
    """Return ``scheme://host[:port]`` for an http(s) URL, or ``None``.

    Scheme and host are lower-cased and a default port is dropped, so the one
    origin a grant lists matches every spelling of it. A URL without an http(s)
    scheme or without a host has no origin a grant could name.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    if ":" in host:  # an IPv6 literal keeps its brackets in an origin
        host = f"[{host}]"
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _check_origin(origin: str) -> str:
    parts = urlsplit(origin)
    normalised = origin_of(origin)
    if (
        normalised is None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
    ):
        raise QgisSdkGrantError(
            f"{origin!r} is not an origin; a grant lists scheme://host[:port] only"
        )
    return normalised


@dataclass(frozen=True, slots=True)
class NetworkGrant:
    """What one view may ask the host's network to do.

    ``origins`` is an explicit allowlist - no wildcards, no suffix matching, no
    "same site". ``methods`` defaults to the read-only pair. ``host_auth`` is
    whether a request may name a QGIS authentication configuration; the view
    still never sees the credential, but spending it is a grant in itself.
    """

    origins: frozenset[str]
    methods: frozenset[str] = field(default_factory=lambda: frozenset({"GET", "HEAD"}))
    host_auth: bool = False
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    max_body_bytes: int = GRANT_MAX_BODY_BYTES
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def __init__(
        self,
        origins: Iterable[str],
        *,
        methods: Iterable[str] = ("GET", "HEAD"),
        host_auth: bool = False,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        max_body_bytes: int = GRANT_MAX_BODY_BYTES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        listed = frozenset(_check_origin(origin) for origin in origins)
        if not listed:
            raise QgisSdkGrantError("a network grant lists at least one origin")
        verbs = frozenset(str(method).upper() for method in methods)
        unknown = sorted(verbs - GRANT_METHODS)
        if unknown:
            raise QgisSdkGrantError(f"{unknown[0]!r} is not a method a grant can allow")
        if not 0 < int(max_body_bytes) <= DEFAULT_MAX_BODY_BYTES:
            raise QgisSdkGrantError(
                f"max_body_bytes must be within 1..{DEFAULT_MAX_BODY_BYTES}"
            )
        if not 0 <= int(max_redirects) <= DEFAULT_MAX_REDIRECTS:
            raise QgisSdkGrantError(
                f"max_redirects must be within 0..{DEFAULT_MAX_REDIRECTS}"
            )
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise QgisSdkGrantError("timeout_seconds must be a positive number")
        object.__setattr__(self, "origins", listed)
        object.__setattr__(self, "methods", verbs)
        object.__setattr__(self, "host_auth", bool(host_auth))
        object.__setattr__(self, "max_redirects", int(max_redirects))
        object.__setattr__(self, "max_body_bytes", int(max_body_bytes))
        object.__setattr__(self, "timeout_seconds", float(timeout_seconds))

    def allows_origin(self, url: str) -> bool:
        """Whether ``url`` sits on one of the granted origins."""
        return origin_of(url) in self.origins

    def constrain(self, request: NetworkRequest) -> NetworkRequest:
        """Return ``request`` held to this grant, or refuse it.

        The refusal names the rule - origin, method, authentication - and the
        origin asked for; never a header, a body or a credential.
        """
        origin = origin_of(request.url)
        if origin is None or origin not in self.origins:
            raise QgisSdkGrantRefusedError(
                f"origin {origin or request.url.split('?')[0]!r} is not granted "
                "to this view"
            )
        if request.method not in self.methods:
            raise QgisSdkGrantRefusedError(
                f"method {request.method} is not granted to this view for {origin}"
            )
        if request.auth_config is not None and not self.host_auth:
            raise QgisSdkGrantRefusedError(
                "host authentication is not granted to this view"
            )
        return replace(
            request,
            timeout_seconds=min(request.timeout_seconds, self.timeout_seconds),
            max_redirects=min(request.max_redirects, self.max_redirects),
            max_body_bytes=min(request.max_body_bytes, self.max_body_bytes),
            allowed_origins=self.origins,
        )


__all__ = [
    "GRANT_MAX_BODY_BYTES",
    "GRANT_METHODS",
    "NetworkGrant",
    "QgisSdkGrantError",
    "origin_of",
]
