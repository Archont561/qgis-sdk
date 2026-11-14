"""Render the inventory's tiers as the table doc-12 carries.

decision-56 consequence: "doc-12 gains a Stability section rendered from the
inventory; the README promises nothing beyond it." This is that renderer, and it
is a function rather than a paragraph so the guide cannot drift from the marks:
the table in the guide is pasted from `qgis-sdk api stability`, and a test fails
when the two disagree.

It follows the support matrix, which is rendered the same way from
`qgis_sdk_tools.targets` for the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["render_stability"]

HEADER = "| Module | Tier | Public names | Deprecated |"
RULE = "| :-- | :-- | :-- | :-- |"


def _deprecated(document: Mapping, module: str) -> int:
    """How many names in one module carry a removal notice."""
    return sum(
        1 for entry in document.get("deprecations", ()) if entry["module"] == module
    )


def render_stability(document: Mapping) -> str:
    """The tier table: one row per public module, in module-name order."""
    rows = [
        f"| `{name}` | {entry['tier']} | {len(entry['names'])} | {_deprecated(document, name)} |"
        for name, entry in sorted(document["modules"].items())
    ]
    return "\n".join([HEADER, RULE, *rows])
