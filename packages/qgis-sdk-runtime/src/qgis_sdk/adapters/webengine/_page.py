"""The restricted page: a ``QWebEnginePage`` that consults the policy.

:func:`create_restricted_page` is the page that installs the :class:`BrowserPolicy`
hooks. Three hooks, all on the page: ``acceptNavigationRequest`` refuses a
navigation (main frame or subframe) the policy does not allow, a request
interceptor blocks every resource request it does not allow - fetch, XHR,
images, scripts, frames, sockets - and ``createWindow`` opens nothing, so a
``window.open`` or ``target=_blank`` cannot leave the policy behind. Page
settings close the remaining doors: no plugins, no script-opened windows, and
Chromium's two local-content switches follow the policy.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis_sdk.models.errors import QgisSdkOptionalDependencyError

from ._policy import BrowserPolicy, Decision
from ._view import WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT

__all__ = ["Refusal", "create_restricted_page"]

Refusal = Callable[[str, Decision], None]


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_create_restricte_p1(_s):
    _s.imported = _import_webengine_core()
    if _s.imported is None:
        raise QgisSdkOptionalDependencyError(
            WEBENGINE_DEPENDENCY, WEBENGINE_INSTALLATION_HINT
        )
    _s.page_class, _s.interceptor_class, _s.settings_class = _s.imported

    def refused(kind: str, decision: Decision) -> None:
        if _s.on_refusal is not None:
            _s.on_refusal(kind, decision)

    _s.refused = refused


def _cc_create_restricte_p2(_s):

    class _Interceptor(_s.interceptor_class):  # type: ignore[misc,valid-type]
        def interceptRequest(self, info: Any) -> None:
            decision = _s.policy.resource(info.requestUrl().toString())
            if not decision.allowed:
                info.block(True)
                _s.refused("resource", decision)

        _s.interceptRequest = interceptRequest

    _s._Interceptor = _Interceptor


def _cc_create_restricte_p3(_s):

    class _RestrictedPage(_s.page_class):  # type: ignore[misc,valid-type]
        def acceptNavigationRequest(
            self, url: Any, navigation_type: Any, is_main_frame: bool
        ) -> bool:
            typed = getattr(type(self).NavigationType, "NavigationTypeTyped", None)
            decision = _s.policy.navigation(
                url.toString(), host_initiated=navigation_type == typed
            )
            if not decision.allowed:
                _s.refused("navigation", decision)
                return False
            return bool(
                super().acceptNavigationRequest(url, navigation_type, is_main_frame)
            )

        _s.acceptNavigationRequest = acceptNavigationRequest

        def createWindow(self, window_type: Any) -> Any:
            _s.refused("window", Decision(False, "", "the page may not open windows"))
            return None

        _s.createWindow = createWindow

    _s._RestrictedPage = _RestrictedPage


def _cc_create_restricte_p4(_s):

    if _s.profile is not None:
        _s.page = _s._RestrictedPage(_s.profile, _s.parent)
    elif _s.parent is not None:
        _s.page = _s._RestrictedPage(_s.parent)
    else:
        _s.page = _s._RestrictedPage()
    _s.interceptor = _s._Interceptor(_s.page)
    _s.page.setUrlRequestInterceptor(_s.interceptor)
    _s.page._qgis_sdk_interceptor = _s.interceptor  # keep it alive with the page
    _s.page._qgis_sdk_policy = _s.policy


def _cc_create_restricte_p5(_s):
    if _s.settings_class is not None:
        _s.attribute = _s.settings_class.WebAttribute
        _s.settings = _s.page.settings()
        for name, value in (
            ("JavascriptCanOpenWindows", False),
            ("LocalContentCanAccessRemoteUrls", bool(_s.policy.origins)),
            ("LocalContentCanAccessFileUrls", bool(_s.policy.asset_roots)),
            ("AllowRunningInsecureContent", False),
            ("PluginsEnabled", False),
            ("PdfViewerEnabled", False),
        ):
            _s.name = name
            _s.value = value
            _s.flag = getattr(_s.attribute, _s.name, None)
            if _s.flag is not None:
                _s.settings.setAttribute(_s.flag, _s.value)


def _cc_create_restricte_p6(_s):
    return _CcReturn(_s.page)


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

    Three hooks: ``acceptNavigationRequest`` refuses a navigation the policy
    does not allow, a request interceptor blocks every resource request it
    does not allow, and ``createWindow`` opens nothing. Page settings close
    the remaining doors: no plugins, no script-opened windows, and Chromium's
    local-content switches follow the policy. ``on_refusal`` receives
    ``("navigation" | "resource" | "window", decision)`` for each refusal.
    """
    _s = _CcState(policy=policy, profile=profile, parent=parent, on_refusal=on_refusal)
    for _p in (
        _cc_create_restricte_p1,
        _cc_create_restricte_p2,
        _cc_create_restricte_p3,
        _cc_create_restricte_p4,
        _cc_create_restricte_p5,
        _cc_create_restricte_p6,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
