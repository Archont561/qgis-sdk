"""The request a server hook reads: plain values, case-insensitive the way OGC is.

``QgsServerRequest`` is a C++ object owned by the server for the length of one
request, and ``QgsServerInterface`` is a QGIS object that cannot exist in a test
(decision-52). Both stay on the adapter side; a hook sees this model, which the
adapter builds once per request and which nothing outside the hook can mutate.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

__all__ = ["CaseInsensitiveMapping", "ServerRequest"]


class CaseInsensitiveMapping(Mapping[str, str]):
    """A read-only mapping whose keys are matched the way HTTP and OGC match them.

    ``params["LAYERS"]``, ``params["layers"]`` and ``params["Layers"]`` are one
    entry, which is what ``QgsServerRequest::getParam`` does for
    ``SERVICE``/``VERSION``/``LAYERS`` and what an author assumes when they read
    an OGC parameter by name. Iteration yields the spellings the caller supplied,
    in their order, so a response that echoes the request echoes what arrived.
    """

    __slots__ = ("_keys", "_values")

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._keys: dict[str, str] = {}
        self._values: dict[str, str] = {}
        for key, value in (values or {}).items():
            folded = str(key).casefold()
            self._keys.setdefault(folded, str(key))
            self._values[folded] = str(value)

    def __getitem__(self, key: str) -> str:
        folded = str(key).casefold()
        if folded in self._values:
            return self._values[folded]
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys.values())

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return ``key`` whatever its case, or ``default``."""
        return self._values.get(str(key).casefold(), default)

    def merged(self, **overrides: str) -> CaseInsensitiveMapping:
        """A copy with ``overrides`` replacing entries of any spelling."""
        values = {
            original: self._values[folded] for folded, original in self._keys.items()
        }
        values.update({str(key): str(value) for key, value in overrides.items()})
        return CaseInsensitiveMapping(values)

    def __repr__(self) -> str:
        entries = ", ".join(f"{key}={self._values[key.casefold()]!r}" for key in self)
        return f"CaseInsensitiveMapping({entries})"


@dataclass(frozen=True, slots=True)
class ServerRequest:
    """One request, as the host received it.

    ``params`` is the merged OGC parameter set (query string plus body for a
    ``POST``), ``headers`` the request headers, and ``body`` the raw bytes.
    ``with_params`` returns a new request, which is how a filter rewrites a
    request without the host having to re-parse anything: the rewritten value
    reaches the hook after it, not the one that already read the old one.
    """

    method: str
    url: str
    params: CaseInsensitiveMapping = field(default_factory=CaseInsensitiveMapping)
    headers: CaseInsensitiveMapping = field(default_factory=CaseInsensitiveMapping)
    body: bytes = b""

    def __post_init__(self) -> None:
        if not isinstance(self.params, CaseInsensitiveMapping):
            object.__setattr__(self, "params", CaseInsensitiveMapping(self.params))
        if not isinstance(self.headers, CaseInsensitiveMapping):
            object.__setattr__(self, "headers", CaseInsensitiveMapping(self.headers))

    def param(self, name: str, default: str | None = None) -> str | None:
        """Return the OGC parameter ``name`` whatever its case, or ``default``."""
        return self.params.get(name, default)

    def header(self, name: str, default: str | None = None) -> str | None:
        """Return the request header ``name`` whatever its case, or ``default``."""
        return self.headers.get(name, default)

    def with_params(self, **overrides: str) -> ServerRequest:
        """A copy with ``overrides`` merged into the parameters."""
        return ServerRequest(
            method=self.method,
            url=self.url,
            params=self.params.merged(**overrides),
            headers=self.headers,
            body=self.body,
        )
