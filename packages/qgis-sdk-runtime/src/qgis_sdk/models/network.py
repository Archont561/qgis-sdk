"""QGIS-free request and response values for the networking surface (decision-4).

A :class:`NetworkRequest` is what a transport receives: already resolved, already
validated, with no credentials in the URL. A :class:`Response` is fully buffered,
which is why the body ceiling is a request value and not a transport setting.
The two limits below were set from measurement, not chosen:

- :data:`DEFAULT_MAX_BODY_BYTES` is the largest response whose hand-over from the
  finished reply to Python stayed inside the 40 ms GUI budget the scheduler is
  held to: 16 MiB took 14-19 ms, 32 MiB took 40-50 ms.
- :data:`DEFAULT_MAX_REDIRECTS` is the browser limit; the SDK transport follows
  each hop itself at about 1 ms per hop on loopback, so 20 hops stay inside the
  same budget. It follows them itself because the real manager was measured
  forwarding ``Authorization`` and ``Cookie`` to a different origin.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Literal

from .errors import QgisSdkDecodeError, QgisSdkHttpStatusError

__all__ = [
    "DEFAULT_MAX_BODY_BYTES",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "Headers",
    "Method",
    "NetworkRequest",
    "Response",
]

DEFAULT_TIMEOUT_SECONDS = 30.0
"""Every request has a timeout; ``None`` at the call site means this one."""

DEFAULT_MAX_REDIRECTS = 20
"""Hops the transport follows before refusing (measured, see module docstring)."""

DEFAULT_MAX_BODY_BYTES = 16 * 1024 * 1024
"""Largest body buffered into a :class:`Response` (measured, see module docstring)."""

Method = Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

_REDACTED_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie"}
)


class Headers(Mapping[str, str]):
    """Immutable, case-insensitive HTTP headers that redact credentials in repr.

    Lookups ignore case; iteration yields the names as they were given. A header
    that appears twice keeps the last value, which is what a buffered client
    needs; the one multi-valued header that matters, ``Set-Cookie``, is not
    something this client manages.
    """

    __slots__ = ("_items",)

    def __init__(
        self, items: Mapping[str, str] | Iterable[tuple[str, str]] | None = None
    ) -> None:
        pairs = items.items() if isinstance(items, Mapping) else (items or ())
        folded: dict[str, tuple[str, str]] = {}
        for name, value in pairs:
            folded[name.lower()] = (name, value)
        self._items = folded

    def __getitem__(self, name: str) -> str:
        return self._items[name.lower()][1]

    def __iter__(self) -> Iterator[str]:
        return (name for name, _value in self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Headers):
            return {k: v for k, (_n, v) in self._items.items()} == {
                k: v for k, (_n, v) in other._items.items()
            }
        return NotImplemented

    def __hash__(self) -> int:
        return hash(tuple(sorted((k, v) for k, (_n, v) in self._items.items())))

    def __repr__(self) -> str:
        shown = ", ".join(
            f"{name!r}: {'<redacted>' if key in _REDACTED_HEADERS else value!r}"
            for key, (name, value) in self._items.items()
        )
        return f"Headers({{{shown}}})"

    def merge(self, other: Mapping[str, str] | None) -> Headers:
        """Return a copy where ``other`` overrides, case-insensitively."""
        if not other:
            return self
        return Headers([*self.items(), *other.items()])

    def without(self, *names: str) -> Headers:
        """Return a copy without the named headers."""
        dropped = {name.lower() for name in names}
        return Headers(
            [
                (name, value)
                for name, value in self.items()
                if name.lower() not in dropped
            ]
        )


@dataclass(frozen=True, slots=True)
class NetworkRequest:
    """One resolved request, as a transport receives it.

    ``url`` is absolute, ``http`` or ``https``, and carries no user-info; the
    client refuses anything else before a transport sees it. ``auth_config`` is
    the id of a QGIS authentication configuration, never a credential. Each
    limit is explicit, so a transport never has to know a client's defaults.

    ``allowed_origins`` is set by a network grant: the origins a redirect may
    lead to, as ``scheme://host[:port]``. Every transport refuses a hop outside
    them with :class:`QgisSdkRedirectError`; ``None`` leaves only the
    transport's own redirect rules in force.
    """

    method: str
    url: str
    headers: Headers = field(default_factory=Headers)
    body: bytes | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    auth_config: str | None = None
    allowed_origins: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class Response:
    """A fully buffered HTTP response.

    ``url`` is where the body came from after redirects. The helpers decode on
    demand and raise :class:`QgisSdkDecodeError` rather than returning garbage;
    :meth:`raise_for_status` is explicit, so a 404 is data until the caller says
    it is an error.
    """

    url: str
    status_code: int
    reason: str
    headers: Headers
    content: bytes
    method: str = "GET"

    @property
    def ok(self) -> bool:
        """Whether the status is below 400."""
        return self.status_code < 400

    @property
    def encoding(self) -> str | None:
        """The charset the ``Content-Type`` header declares, if any."""
        content_type = self.headers.get("content-type", "")
        for parameter in content_type.split(";")[1:]:
            name, _sep, value = parameter.strip().partition("=")
            if name.strip().lower() == "charset":
                return value.strip().strip('"') or None
        return None

    @property
    def text(self) -> str:
        """The body decoded with its declared charset, else UTF-8."""
        encoding = self.encoding or "utf-8"
        try:
            return self.content.decode(encoding)
        except (UnicodeDecodeError, LookupError) as error:
            raise QgisSdkDecodeError(
                f"the body is not valid {encoding} text: {error}",
                method=self.method,
                url=self.url,
            ) from error

    def json(self) -> object:
        """The body parsed as JSON."""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as error:
            raise QgisSdkDecodeError(
                f"the body is not valid JSON: {error.msg} at position {error.pos}",
                method=self.method,
                url=self.url,
            ) from error

    def raise_for_status(self) -> Response:
        """Raise :class:`QgisSdkHttpStatusError` on 4xx/5xx; return self otherwise."""
        if self.status_code >= 400:
            raise QgisSdkHttpStatusError(
                self.status_code, self.reason, method=self.method, url=self.url
            )
        return self
