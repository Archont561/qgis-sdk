"""The one diagnostic builder: ``API001``."""

from __future__ import annotations

import ast
from pathlib import Path

from qgis_sdk.deprecation import Deprecation

from ..diagnostics import Diagnostic

__all__ = ["deprecated_diagnostic"]


def deprecated_diagnostic(
    *, module: str, name: str, mark: Deprecation, node: ast.AST, path: Path
) -> Diagnostic:
    """``API001`` for one import of a name the SDK is retiring."""
    dotted = f"{module}.{name}"
    remedy = f"; use {mark.use} instead" if mark.use else ""
    return Diagnostic(
        rule="API001",
        path=path,
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
        message=(
            f"`{dotted}` is deprecated since {mark.since} and will be removed in "
            f"{mark.removal}{remedy}"
        ),
        remediation=(
            f"Switch to the replacement before {mark.removal}: the name keeps "
            "working until then, and removing it earlier would break a promise "
            "the SDK made (decision-56)."
        ),
        severity="warning",
    )
