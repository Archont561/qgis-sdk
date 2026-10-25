"""Optional Qt WebEngine host support for QGIS-aware deployments.

The SDK core remains QGIS-free. This adapter probes for the Qt WebEngine
Python bindings lazily and reports an actionable SDK error when a deployment
has not provisioned them. It never imports Qt, PyQt, or QGIS while the module
is imported.

It also carries the browser half of decision-20. The bridge's grants constrain
what a page may ask the *host* to do; nothing about them stops the page's own
``fetch``, ``<img>``, ``<iframe>`` or ``location`` from reaching an origin the
host never granted. :class:`BrowserPolicy` is the pure allowlist both Qt hooks
consult - :meth:`QWebEnginePage.acceptNavigationRequest` for navigations and a
``QWebEngineUrlRequestInterceptor`` for every resource request - and
:func:`create_restricted_page` is the page that installs them. The policy is
decided here so it can be tested without Chromium; the real-browser test proves
the hooks consult it. It is an egress allowlist, not a sandbox: it does not
claim to contain a compromised renderer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from qgis_sdk.models.errors import QgisSdkBridgeError, QgisSdkOptionalDependencyError
from qgis_sdk.network.grants import origin_of

WEBENGINE_DEPENDENCY = "pyqt6-webengine"
WEBENGINE_INSTALLATION_HINT = (
    "Install the Qt WebEngine Python bindings provided by the QGIS "
    "distribution for this platform (for example python3-pyqt6-webengine on "
    "Debian/Ubuntu or the matching OSGeo4W/macOS package). The SDK does not "
    "download or install Qt WebEngine itself."
)


def _import_webengine_view() -> Any | None:
    """Return the ``QWebEngineView`` class if its bindings are installed."""
    candidates = (
        ("qgis.PyQt.QtWebEngineWidgets", "QWebEngineView"),
        ("PyQt6.QtWebEngineWidgets", "QWebEngineView"),
        ("PyQt5.QtWebEngineWidgets", "QWebEngineView"),
    )
    for module_name, class_name in candidates:
        try:
            module = __import__(module_name, fromlist=(class_name,))
        except ImportError:
            continue
        view_class = getattr(module, class_name, None)
        if view_class is not None:
            return view_class
    return None


def webengine_available() -> bool:
    """Return whether a Qt WebEngine view can be created in this runtime."""
    return _import_webengine_view() is not None


def require_webengine() -> None:
    """Raise an actionable error unless Qt WebEngine view bindings exist."""
    if not webengine_available():
        raise QgisSdkOptionalDependencyError(
            WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT
        )


def create_webengine_view(*args: Any, **kwargs: Any) -> Any:
    """Create a ``QWebEngineView`` or raise an actionable SDK error."""
    view_class = _import_webengine_view()
    if view_class is None:
        raise QgisSdkOptionalDependencyError(
            WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT
        )
    return view_class(*args, **kwargs)


# -- the egress policy -------------------------------------------------------

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
        if url in _ALWAYS:
            return Decision(True, url, "the page's own empty document")
        scheme = urlsplit(url).scheme.lower() if url else ""
        if scheme == "qrc":
            if self.allow_qrc:
                return Decision(True, url, "packaged content")
            return Decision(False, url, "qrc: content is not allowed by this policy")
        if scheme == "data":
            if navigation and not host_initiated:
                return Decision(
                    False, "data:...", "a data: navigation is the host's to make"
                )
            return Decision(True, "data:...", "inline content carries no egress")
        if scheme == "blob":
            inner = _egress_origin(url[len("blob:") :])
            if inner is not None and inner in self.origins:
                return Decision(True, shown, f"a blob of the granted origin {inner}")
            return Decision(False, shown, "a blob of an origin that was not granted")
        if scheme == "file":
            return self._file(url, shown)
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


# -- the restricted page -----------------------------------------------------

Refusal = Callable[[str, Decision], None]


def _import_webengine_core() -> tuple[Any, Any, Any] | None:
    """Return ``(QWebEnginePage, QWebEngineUrlRequestInterceptor, QWebEngineSettings)``."""
    candidates = (
        ("qgis.PyQt.QtWebEngineCore", "qgis.PyQt.QtWebEngineCore"),
        ("PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineCore"),
        ("PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore"),
    )
    for page_module, core_module in candidates:
        try:
            pages = __import__(page_module, fromlist=("QWebEnginePage",))
            core = __import__(
                core_module, fromlist=("QWebEngineUrlRequestInterceptor",)
            )
        except ImportError:
            continue
        page = getattr(pages, "QWebEnginePage", None)
        interceptor = getattr(core, "QWebEngineUrlRequestInterceptor", None)
        settings = getattr(pages, "QWebEngineSettings", None) or getattr(
            core, "QWebEngineSettings", None
        )
        if page is not None and interceptor is not None:
            return page, interceptor, settings
    return None


def create_restricted_page(
    policy: BrowserPolicy,
    *,
    profile: Any | None = None,
    parent: Any | None = None,
    on_refusal: Refusal | None = None,
) -> Any:
    """Create a ``QWebEnginePage`` that consults ``policy`` for every egress.

    Three hooks, all on the page: ``acceptNavigationRequest`` refuses a
    navigation (main frame or subframe) the policy does not allow, a request
    interceptor blocks every resource request it does not allow - fetch, XHR,
    images, scripts, frames, sockets - and ``createWindow`` opens nothing, so a
    ``window.open`` or ``target=_blank`` cannot leave the policy behind. Page
    settings close the remaining doors: no plugins, no script-opened windows,
    and Chromium's two local-content switches follow the policy - local
    content (``file:``, ``qrc:``) may load ``file:`` subresources only when
    the policy names asset roots and may reach remote URLs only when it grants
    origins; the interceptor is what confines both to the list.

    ``on_refusal`` receives ``("navigation" | "resource" | "window", decision)``
    for each refusal, for the host's log; nothing is reported to the page
    beyond the failed load it observes anyway.
    """
    imported = _import_webengine_core()
    if imported is None:
        raise QgisSdkOptionalDependencyError(
            WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT
        )
    page_class, interceptor_class, settings_class = imported

    def refused(kind: str, decision: Decision) -> None:
        if on_refusal is not None:
            on_refusal(kind, decision)

    class _Interceptor(interceptor_class):  # type: ignore[misc,valid-type]
        def interceptRequest(self, info: Any) -> None:
            decision = policy.resource(info.requestUrl().toString())
            if not decision.allowed:
                info.block(True)
                refused("resource", decision)

    class _RestrictedPage(page_class):  # type: ignore[misc,valid-type]
        def acceptNavigationRequest(
            self, url: Any, navigation_type: Any, is_main_frame: bool
        ) -> bool:
            typed = getattr(type(self).NavigationType, "NavigationTypeTyped", None)
            decision = policy.navigation(
                url.toString(), host_initiated=navigation_type == typed
            )
            if not decision.allowed:
                refused("navigation", decision)
                return False
            return bool(
                super().acceptNavigationRequest(url, navigation_type, is_main_frame)
            )

        def createWindow(self, window_type: Any) -> Any:
            refused("window", Decision(False, "", "the page may not open windows"))
            return None

    page = (
        _RestrictedPage(profile, parent)
        if profile is not None
        else (_RestrictedPage(parent) if parent is not None else _RestrictedPage())
    )
    interceptor = _Interceptor(page)
    page.setUrlRequestInterceptor(interceptor)
    page._qgis_sdk_interceptor = interceptor  # keep it alive with the page
    page._qgis_sdk_policy = policy
    if settings_class is not None:
        attribute = settings_class.WebAttribute
        settings = page.settings()
        for name, value in (
            ("JavascriptCanOpenWindows", False),
            ("LocalContentCanAccessRemoteUrls", bool(policy.origins)),
            ("LocalContentCanAccessFileUrls", bool(policy.asset_roots)),
            ("AllowRunningInsecureContent", False),
            ("PluginsEnabled", False),
            ("PdfViewerEnabled", False),
        ):
            flag = getattr(attribute, name, None)
            if flag is not None:
                settings.setAttribute(flag, value)
    return page


__all__ = [
    "WEBENGINE_DEPENDENCY",
    "WEBENGINE_INSTALLATION_HINT",
    "BrowserPolicy",
    "Decision",
    "create_restricted_page",
    "create_webengine_view",
    "require_webengine",
    "webengine_available",
]
