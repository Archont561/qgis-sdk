"""Reading ``pyproject.toml`` into a validated :class:`ProjectConfig`."""

from __future__ import annotations

from pathlib import Path

from qgis_sdk_tools.check.diagnostics import Diagnostic
from qgis_sdk_tools.manifest import read_pyproject, table

from ._facts import (
    _PLUGIN_SPEC,
    PYPROJECT,
    ProjectConfig,
    QgisSdkProjectError,
    _ProjectFacts,
    config_from_facts,
    plugin_spec_finding,
    read_project_fields,
    read_tool_fields,
)


def load_project(root: Path) -> tuple[ProjectConfig | None, tuple[Diagnostic, ...]]:
    """Read the configuration at ``root``; ``None`` plus findings when unusable.

    Findings that do not stop the configuration from being used (a missing
    ``[project] description``, say) come back beside a config; ``check``
    prints them all, ``build`` refuses on the errors.
    """
    from ._externals import missing_plugin

    root = Path(root)
    data, malformed = read_pyproject(root / PYPROJECT)
    if data is None:
        if malformed is not None:
            return (
                None,
                (),
            )  # CONFIG001 from check_project already names the parse error
        return None, (missing_plugin(f"{root} has no {PYPROJECT}"),)
    tool = table(data, "tool", "qgis-sdk") or {}
    spec = tool.get("plugin")
    if not isinstance(spec, str) or _PLUGIN_SPEC.match(spec) is None:
        return None, (plugin_spec_finding(spec),)
    facts = _ProjectFacts(root, spec, tool)
    read_project_fields(facts, table(data, "project") or {})
    read_tool_fields(facts)
    return config_from_facts(facts)


def require_project(root: Path) -> ProjectConfig:
    """The configuration, or :class:`QgisSdkProjectError` naming what is wrong."""
    config, findings = load_project(root)
    errors = tuple(d for d in findings if d.severity == "error")
    if config is None:
        if not errors:
            errors = (config(f"{PYPROJECT} does not parse", "Fix the TOML first."),)
        raise QgisSdkProjectError(errors, Path(root))
    if errors:
        raise QgisSdkProjectError(errors, Path(root))
    return config
