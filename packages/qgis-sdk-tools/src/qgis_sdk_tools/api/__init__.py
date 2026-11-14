"""The public API as a document: dump it, diff it, gate on it.

decision-56 makes a generated inventory the contract for 1.0 rather than a page
somebody edits. Three pieces do that:

* :func:`inventory` reads the installed tree - public modules and their
  signatures, check rule ids, host operations, CLI commands.
* :func:`diff` compares two inventories and classifies every change as additive,
  deprecating or breaking.
* :func:`refusals` turns that classification into the reason a release cannot
  ship at the version it declares.

``qgis-sdk api dump`` and ``release verify-api`` are thin wrappers; the logic
lives here so a test can call it without a checkout.
"""

from __future__ import annotations

from qgis_sdk_tools.api._inventory import (
    API_VERSION,
    PUBLIC_MODULES,
    Inventory,
    inventory,
    read,
    write,
)
from qgis_sdk_tools.api._render import render_stability
from qgis_sdk_tools.api._verify import (
    Change,
    consequence,
    diff,
    early_removals,
    refusals,
    verdict,
)

__all__ = [
    "API_VERSION",
    "PUBLIC_MODULES",
    "Change",
    "Inventory",
    "consequence",
    "diff",
    "early_removals",
    "inventory",
    "read",
    "refusals",
    "render_stability",
    "verdict",
    "write",
]
