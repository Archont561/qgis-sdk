"""The three diagnostic builders: JOB001, JOB002, JOB003."""

from __future__ import annotations

import ast
from pathlib import Path

from ..diagnostics import Diagnostic

__all__ = ["context_diagnostic", "dynamic_diagnostic", "gui_diagnostic"]


def gui_diagnostic(
    job: str,
    dotted: str,
    node: ast.expr,
    path: Path,
    *,
    attribute: str | None = None,
) -> Diagnostic:
    """``JOB001`` for one piece of GUI state a job body reaches."""
    shown = f"`{attribute}` (bound to `{dotted}`)" if attribute else f"`{dotted}`"
    return Diagnostic(
        rule="JOB001",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"job `{job}` reaches {shown} in its body, which belongs to the GUI thread"
        ),
        remediation=(
            "Do the GUI work on the driving thread: open the surface or read the "
            "interface in an action, pass plain values (paths, ids, numbers) into the "
            "job, and update the UI in the success callback (decision-65)."
        ),
    )


def context_diagnostic(
    job: str, context: str, node: ast.expr, path: Path
) -> Diagnostic:
    """``JOB002`` for one driving-thread capability read from a job body."""
    attribute = getattr(node, "attr", "")
    return Diagnostic(
        rule="JOB002",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"job `{job}` reads `{context}.{attribute}` in its body, which a "
            "WorkerContext refuses"
        ),
        remediation=(
            f"A job body only gets `progress` and `cancellation`. Pass plain values "
            f"in and re-read `{attribute}` from the success callback, which runs on "
            "the driving thread (decision-65)."
        ),
    )


def dynamic_diagnostic(job: str, node: ast.expr, path: Path) -> Diagnostic:
    """``JOB003`` for a by-name import this check cannot follow."""
    return Diagnostic(
        rule="JOB003",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"job `{job}` imports a module by name, so what the body reaches "
            "cannot be read"
        ),
        remediation=(
            "Import the module at module level or in a helper outside the job, so "
            "`qgis-sdk check` can see what the body touches; this is a warning about "
            "what the check cannot prove, not an error."
        ),
        severity="warning",
    )
