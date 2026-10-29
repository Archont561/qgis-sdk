"""Build-time findings on top of ``check_project``: the page the ZIP must carry.

Same :class:`Diagnostic` shape as ``check`` so the build prints one list.
(``ENTRY001`` - no ``classFactory`` - retired with decision-43: the build
binds it itself, and ``check`` reports a hand-written one as ``ENTRY002``.)

The dependency rules moved to ``check`` in decision-50 point 3: every import
is bucketed there, so ``DEP001`` (unknown root), ``DEP002``
(``qgis_sdk.testing``), ``DEP003`` (a compiled distribution cannot be
vendored) and ``DEP004`` (a declared vendored distribution is missing, or one
of its requirements is neither vendored nor external) surface before a build
runs, not first from it.

``WEB001``
    The project has a web UI but no built page to ship.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from qgis_sdk_tools.check import Diagnostic

__all__ = ["check_web_assets"]


def check_web_assets(assets: Path, plugin: str) -> Iterator[Diagnostic]:
    """``WEB001`` when a web project has no built page under ``<plugin>/web``."""
    if (assets / "index.html").is_file():
        return
    yield Diagnostic(
        rule="WEB001",
        path=Path(plugin) / "web",
        line=0,
        column=0,
        message="the project has a web UI but no built page to ship",
        remediation=(
            "Run the web build (`qgis-sdk build` does it when web/node_modules "
            "exists) or build it yourself before passing --no-web."
        ),
    )
