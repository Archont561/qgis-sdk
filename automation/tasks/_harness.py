"""The harness, available to a task graph: logs, annotations, and reports."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from automation import ci, commits, results

__all__ = [
    "annotate_coverage",
    "annotate_log",
    "commit_base",
    "report_bun",
    "report_steps",
    "run_log",
    "test_results",
]


def run_log(log: str, command: Sequence[str] | None = None) -> int:
    """Run ``command``, keeping its output in ``log`` for a later annotation."""
    return ci.run_logged(list(command or []), Path(log))


def annotate_log(
    log: str, title: str = "failed step", tail: int = 25, skip_missing: bool = False
) -> int:
    """Turn the tail of a captured log into a workflow annotation."""
    ci.annotate_log(Path(log), title=title, tail=tail, skip_missing=skip_missing)
    return 0


def annotate_coverage(log: str) -> int:
    """Annotate the coverage failures of a captured coverage log."""
    ci.annotate_coverage(Path(log))
    return 0


def report_bun(log: str, title: str) -> int:
    """Annotate the failing JavaScript tests of a captured log."""
    ci.report_bun(Path(log), title)
    return 0


def report_steps() -> int:
    """Summarise every failed workflow step that recorded itself."""
    ci.report_steps()
    return 0


def commit_base() -> int:
    """Publish ``BASE_SHA``/``BASE_REF`` for the commit-message gate."""
    return commits.main()


def test_results(report: str, title: str = "") -> int:
    """Turn a JUnit XML report into the failure annotation a job shows."""
    return results.main([report, *(["--title", title] if title else [])])
