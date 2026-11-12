"""Preflight: check the next revision before the running one is touched."""

from __future__ import annotations

from pathlib import Path

from qgis_sdk_tools.check import check_project

from ._types import ADVISORY_RULES, PROJECT_RULES, UNWATCHED

__all__ = ["preflight"]


def preflight(root: Path, plugin: str) -> tuple[list[str], list[str]]:
    """Check the next revision before the running one is touched.

    Returns ``(problems, warnings)``: problems refuse the reload (a module
    that does not compile, metadata QGIS would reject, a project ``check``
    cannot read), warnings are advisory findings about the plugin package
    (native imports outside the adapter, layer violations). Findings outside
    the plugin package - the project's tests, say - never block a reload.
    """
    root = Path(root)
    package = root / plugin
    problems: list[str] = []
    warnings: list[str] = []
    for path in sorted(package.rglob("*.py")):
        if any(part in UNWATCHED for part in path.relative_to(package).parts):
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            where = path.relative_to(root).as_posix()
            problems.append(f"{where}:{error.lineno}: {error.msg}")
    return _preflight_tail1(**{**globals(), **locals()})


def _preflight_tail1(**values):
    plugin = values["plugin"]
    problems = values["problems"]
    root = values["root"]
    warnings = values["warnings"]
    if problems:
        return problems, warnings  # check_project would only repeat them
    report = check_project(root)
    for finding in report.diagnostics:
        if finding.severity != "error":
            continue
        parts = finding.path.parts
        in_package = parts[:1] == (plugin,)
        is_project_shape = finding.rule.startswith(PROJECT_RULES)
        if not (in_package or is_project_shape):
            continue
        line = f"{finding.path.as_posix()}: {finding.rule} {finding.message}"
        if finding.rule in ADVISORY_RULES:
            warnings.append(line)
        else:
            problems.append(line)
    return problems, warnings
