"""The curated host surface a web view may call, and the wiring that answers it.

Decision-27 draws the line this module implements: a page may reach the five
curated Protocols in :mod:`qgis_sdk.services` - and nothing else of the QGIS API.
What a page gets is not "the host": it is a declared list of operations, each
with a request and a result schema, a canonical grant, a thread affinity and the
Protocol method it wraps. The same list is what the TypeScript module in
``@archont561/qgis-sdk/host`` is generated from, so the surface a page
sees cannot drift from the surface the host answers.

Two rules are enforced by the declaration rather than by review:

* **Deferred is a recorded decision.** Every method of a curated Protocol is
  either one of :data:`HOST_OPERATIONS` or one of
  :data:`DEFERRED_HOST_METHODS` with the reason it is absent. A test reflects
  the Protocols and fails when a method appears in neither, so adding a Protocol
  method cannot quietly become an unreachable - or, worse, an unintentionally
  reachable - part of the wire surface.
* **No page-supplied paths, no unbounded arrays.** Nothing here takes a
  filesystem path: ``layers.open_vector`` and ``files.export`` take a
  host-minted ``FileRef`` (:mod:`qgis_sdk.bridge.authority`) that is resolved
  against the calling view, and every list that can grow is paged by
  :func:`_page` before it crosses ``QWebChannel``.
* **Nothing slow is a call.** ``network.fetch`` is a stream: the request goes
  out through the view's network grant and the reply arrives as one event on
  a later event-loop turn, so the GUI thread never waits on a socket.

Beyond the read-only operations and ``styles.apply``, the surface carries the
authority operations: an open through a file ref, an export through a file ref, and a
fetch through a network grant. Each is refused with its own code when the ref
or grant does not cover what was asked (decision-20).
"""

from __future__ import annotations

from qgis_sdk.bridge.host._handlers import register_host_operations
from qgis_sdk.bridge.host._operations import (
    DEFERRED_HOST_METHODS,
    HOST_OPERATIONS,
    HostOperation,
    granted_operations,
    host_description,
    host_grant_names,
    host_grants,
    host_operation_ids,
)
from qgis_sdk.bridge.host._schemas import DEFAULT_PAGE, MAX_PAGE
from qgis_sdk.bridge.host._services import HostServices
from qgis_sdk.models.features import DEFAULT_FEATURE_PAGE, MAX_FEATURE_PAGE

__all__ = [
    "DEFAULT_FEATURE_PAGE",
    "DEFAULT_PAGE",
    "DEFERRED_HOST_METHODS",
    "HOST_OPERATIONS",
    "MAX_FEATURE_PAGE",
    "MAX_PAGE",
    "HostOperation",
    "HostServices",
    "granted_operations",
    "host_description",
    "host_grant_names",
    "host_grants",
    "host_operation_ids",
    "register_host_operations",
]

#: Rows a page gets when it does not ask for a size.
