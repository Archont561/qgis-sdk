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

from ._page import Refusal, create_restricted_page
from ._page import _import_webengine_core as _import_webengine_core
from ._policy import BrowserPolicy, Decision
from ._view import (
    WEBENGINE_DEPENDENCY,
    WEBENGINE_INSTALLATION_HINT,
    create_webengine_view,
    require_webengine,
    webengine_available,
)

__all__ = [
    "WEBENGINE_DEPENDENCY",
    "WEBENGINE_INSTALLATION_HINT",
    "BrowserPolicy",
    "Decision",
    "Refusal",
    "create_restricted_page",
    "create_webengine_view",
    "require_webengine",
    "webengine_available",
]
