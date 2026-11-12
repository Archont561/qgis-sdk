"""The browser half of decision-20: the egress allowlist a page obeys.

The bridge's grants constrain what a page may ask the *host* to do; nothing
about them stops the page's own ``fetch``, ``<img>``, ``<iframe>`` or
``location`` from reaching an origin the host never granted. :class:`BrowserPolicy`
is the pure allowlist both Qt hooks consult - :meth:`QWebEnginePage.acceptNavigationRequest`
for navigations and a ``QWebEngineUrlRequestInterceptor`` for every resource
request. The policy is decided here so it can be tested without Chromium; the
real-browser test proves the hooks consult it. It is an egress allowlist, not a
sandbox: it does not claim to contain a compromised renderer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.network.grants import origin_of

__all__ = ["BrowserPolicy", "Decision"]

_SOCKET_SCHEMES = {"ws": "http", "wss": "https"}
_ALWAYS = frozenset({"about:blank", "about:srcdoc"})


@dataclass(frozen=True, slots=True)
class Decision:
    """What the policy decided about one URL, and why - without its query."""

    allowed: bool
    url: str
    reason: str


def _egress_origin(url: str) -> str | None:
    """The http(s) origin of ``url``, with WebSocket schemes folded in."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in _SOCKET_SCHEMES:
        url = _SOCKET_SCHEMES[scheme] + url[len(scheme) :]
    return origin_of(url)


def _shown(url: str) -> str:
    """The URL without its query or fragment: a reason must not log a token."""
    parts = urlsplit(url)
    return parts._replace(query="", fragment="").geturl() if parts.scheme else url


@dataclass(frozen=True)
class BrowserPolicy:
    """The origins and asset roots a view's page may load from and talk to.

    ``origins`` are http(s) origins, exact: a dev server such as
    ``http://127.0.0.1:5173`` and the APIs the page calls directly. ``ws`` and
    ``wss`` map onto them, so a dev server's HMR socket needs no extra entry.
    ``asset_roots`` are directories whose files the page may load over
    ``file:``; anything resolving outside them - traversal, a symlink out - is
    refused. ``qrc:`` is the host's own packaged content and always allowed;
    ``data:`` and ``blob:`` carry no egress of their own and are allowed as
    resources, while a ``data:`` *navigation* is only allowed when the host
    made it (``setHtml``). Everything else is refused: a scheme the policy
    does not name is not an origin it granted.
    """

    origins: frozenset[str] = frozenset()
    asset_roots: tuple[Path, ...] = ()
    allow_qrc: bool = True

    def __init__(
        self,
        *,
        origins: Iterable[str] = (),
        asset_roots: Iterable[str | Path] = (),
        allow_qrc: bool = True,
    ) -> None:
        listed: set[str] = set()
        for origin in origins:
            normalised = _egress_origin(origin)
            parts = urlsplit(origin)
            if normalised is None or parts.path not in ("", "/") or parts.query:
                raise QgisSdkBridgeError(
                    f"{origin!r} is not an origin; the policy lists "
                    "scheme://host[:port] only"
                )
            listed.add(normalised)
        roots: list[Path] = []
        for root in asset_roots:
            resolved = Path(root).expanduser().resolve()
            if not resolved.is_dir():
                raise QgisSdkBridgeError(
                    f"asset root {Path(root).name!r} is not a directory that exists"
                )
            roots.append(resolved)
        object.__setattr__(self, "origins", frozenset(listed))
        object.__setattr__(self, "asset_roots", tuple(roots))
        object.__setattr__(self, "allow_qrc", bool(allow_qrc))

    def resource(self, url: str) -> Decision:
        """Decide a resource request: subresource, fetch, frame, socket."""
        return self._decide(url, host_initiated=False, navigation=False)

    def navigation(self, url: str, *, host_initiated: bool = False) -> Decision:
        """Decide a navigation; ``host_initiated`` is a load the host asked for."""
        return self._decide(url, host_initiated=host_initiated, navigation=True)

    def _decide(self, url: str, *, host_initiated: bool, navigation: bool) -> Decision:
        shown = _shown(url)
        scheme = urlsplit(url).scheme.lower() if url else ""
        if scheme == "qrc":
            return self._qrc(url)
        if scheme == "data":
            return self._data(navigation, host_initiated)
        if scheme == "blob":
            return self._blob(url, shown)
        if scheme == "file":
            return self._file(url, shown)
        return self._origin(url, shown, scheme)

    def _qrc(self, url: str) -> Decision:
        """``qrc:`` is packaged content, allowed only when the policy opts in."""
        if self.allow_qrc:
            return Decision(True, url, "packaged content")
        return Decision(False, url, "qrc: content is not allowed by this policy")

    def _data(self, navigation: bool, host_initiated: bool) -> Decision:
        """``data:`` carries no egress, but only the host may navigate to it."""
        if navigation and not host_initiated:
            return Decision(
                False, "data:...", "a data: navigation is the host's to make"
            )
        return Decision(True, "data:...", "inline content carries no egress")

    def _blob(self, url: str, shown: str) -> Decision:
        """A blob inherits the egress origin it was minted from."""
        inner = _egress_origin(url[len("blob:") :])
        if inner is not None and inner in self.origins:
            return Decision(True, shown, f"a blob of the granted origin {inner}")
        return Decision(False, shown, "a blob of an origin that was not granted")

    def _origin(self, url: str, shown: str, scheme: str) -> Decision:
        """Everything else is decided by comparing its origin with the grant."""
        if url in _ALWAYS:
            return Decision(True, url, "the page's own empty document")
        origin = _egress_origin(url)
        if origin is None:
            return Decision(
                False, shown, f"{scheme or 'no'} scheme is not one this policy grants"
            )
        if origin in self.origins:
            return Decision(True, shown, f"granted origin {origin}")
        return Decision(False, shown, f"origin {origin} is not granted to this view")

    def _file(self, url: str, shown: str) -> Decision:
        parts = urlsplit(url)
        if parts.netloc not in ("", "localhost"):
            return Decision(False, shown, "a file: URL with a host is refused")
        try:
            path = Path(url2pathname(parts.path)).resolve()
        except (OSError, ValueError):
            return Decision(False, shown, "the file: path cannot be resolved")
        for root in self.asset_roots:
            if path == root or root in path.parents:
                return Decision(True, shown, f"under asset root {root.name!r}")
        return Decision(False, shown, "a file outside the asset roots")
