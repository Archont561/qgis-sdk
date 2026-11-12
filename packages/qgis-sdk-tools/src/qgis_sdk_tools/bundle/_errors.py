"""``qgis-sdk build``: a validated, installable plugin ZIP (decision-8).

``build_plugin`` is the library the command calls. In order:

1. ``check_project`` plus the build-only rules in :mod:`.validate`; any
   error refuses the build with the same diagnostics ``check`` prints.
2. The web page, when the project has one: run the project's own build
   script (never install anything) or ship a page already built.
3. Stage the plugin package without caches, tests and tooling state, add
   the host artifacts the source does not carry (decision-43): the
   ``metadata.txt`` rendered from ``pyproject.toml`` and the
   ``classFactory = host(...)`` line appended to ``<plugin>/__init__.py``;
   add the runtime under ``<plugin>/_vendor/qgis_sdk`` with imports
   rewritten (:mod:`.vendor`), and write a reproducible ZIP whose only root
   entry is the plugin directory - what QGIS's *Install from ZIP* expects.

The runtime that is vendored is the one this interpreter imports; the
project's own requirement on it is checked (``VERSION003``/``VERSION004``)
and recorded in the NOTICE, never installed.
"""

from __future__ import annotations

import tempfile as _tempfile
from collections.abc import Callable as _Callable
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path
from typing import Final as _Final
from typing import Literal as _Literal

from qgis_sdk.models import QgisSdkError as _QgisSdkError

from qgis_sdk_tools.artifacts import (
    METADATA_FILE as _METADATA_FILE,
)
from qgis_sdk_tools.artifacts import (
    QgisSdkArtifactError as _QgisSdkArtifactError,
)
from qgis_sdk_tools.artifacts import (
    introspect_plugin as _introspect_plugin,
)
from qgis_sdk_tools.artifacts import (
    render_metadata as _render_metadata,
)
from qgis_sdk_tools.bundle.validate import check_web_assets as _check_web_assets
from qgis_sdk_tools.bundle.vendor import (
    RUNTIME_PACKAGE as _RUNTIME_PACKAGE,
)
from qgis_sdk_tools.bundle.vendor import (
    notice as _notice,
)
from qgis_sdk_tools.bundle.vendor import (
    runtime_version as _runtime_version,
)
from qgis_sdk_tools.bundle.vendor import (
    stage_vendored as _stage_vendored,
)
from qgis_sdk_tools.bundle.vendor import (
    vendored_roots as _vendored_roots,
)
from qgis_sdk_tools.check import CheckReport as _CheckReport
from qgis_sdk_tools.check import Diagnostic as _Diagnostic
from qgis_sdk_tools.check import check_project as _check_project
from qgis_sdk_tools.check.versions import resolve_runtime as _resolve_runtime
from qgis_sdk_tools.devtools.dev import QgisSdkDevError as _QgisSdkDevError
from qgis_sdk_tools.devtools.dev import inspect_project as _inspect_project
from qgis_sdk_tools.distributions import (
    Distribution as _Distribution,
)
from qgis_sdk_tools.project import ProjectConfig as _ProjectConfig

VENDOR_PACKAGE: _Final = "_vendor"
OUTPUT_DIRECTORY: _Final = "dist"
EXCLUDED_DIRECTORIES: _Final = frozenset(
    {
        "__pycache__",
        "tests",
        "test",
        ".qgis-sdk",
        ".pytest_cache",
        ".git",
        "node_modules",
    }
)
EXCLUDED_SUFFIXES: _Final = frozenset({".pyc", ".pyo"})
EXCLUDED_FILES: _Final = frozenset({".DS_Store"})
ZIP_EPOCH: _Final = (1980, 1, 1, 0, 0, 0)
RunProcess = _Callable[[_Sequence[str], _Path], int]
WebOutcome = _Literal["none", "built", "prebuilt"]


class QgisSdkBuildError(_QgisSdkError):
    """The build cannot run: not a project, a web build failed, no interpreter."""


class QgisSdkBuildRefusedError(QgisSdkBuildError):
    """The project has findings QGIS would not forgive; nothing was written."""

    def __init__(self, diagnostics: _Sequence[_Diagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        errors = sum(1 for d in self.diagnostics if d.severity == "error")
        super().__init__(
            f"build refused: {errors} error{'s' if errors != 1 else ''}; "
            "fix them and build again"
        )


@_dataclass(frozen=True, slots=True)
class BuildResult:
    """What was built, and the findings that did not stop it."""

    archive: _Path
    plugin: str
    version: str
    files: tuple[str, ...]
    report: _CheckReport
    runtime_version: str
    web: WebOutcome
    external: tuple[str, ...]
    runtime_requirement: str | None = None
    vendored: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "archive": str(self.archive),
            "plugin": self.plugin,
            "version": self.version,
            "files": len(self.files),
            "runtime_version": self.runtime_version,
            "runtime_requirement": self.runtime_requirement,
            "web": self.web,
            "external": list(self.external),
            "vendored": list(self.vendored),
            "report": self.report.to_json(),
        }


@_dataclass(frozen=True, slots=True)
class _BuildPlan:
    """Everything staging and the final result need, resolved once."""

    project: object
    report: _CheckReport
    web_outcome: WebOutcome
    vendored: _Sequence[_Distribution]
    plugin: str
    version: str
    archive: _Path
    resolution: object
    runtime: str
    prefix: str
    roots: tuple[str, ...]
    external: _Sequence[str]
    facts: object


def _load_project(root: _Path):
    """Read the project, translating a dev error into a build error."""
    try:
        return _inspect_project(root)
    except _QgisSdkDevError as error:
        raise QgisSdkBuildError(str(error)) from error


def _build_report(project, plugin, assets, web, run) -> tuple[_CheckReport, WebOutcome]:
    """Run ``check`` plus the build-only rules; refuse on any error."""
    from ._build import build_web

    report = _check_project(project.root)
    diagnostics = list(report.diagnostics)
    web_outcome: WebOutcome = "none"
    if project.web is not None:
        if web:
            build_web(project.web, run)
            web_outcome = "built"
        else:
            web_outcome = "prebuilt"
        diagnostics.extend(_check_web_assets(assets, plugin))
    diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))
    report = _CheckReport(
        root=project.root,
        diagnostics=tuple(diagnostics),
        files_checked=report.files_checked,
    )
    if not report.ok:
        raise QgisSdkBuildRefusedError(report.diagnostics)
    return report, web_outcome


@_dataclass(frozen=True, slots=True)
class _BuildPlanInputs:
    """The validated facts one build plan closes over."""

    project: object
    report: _CheckReport
    web_outcome: WebOutcome
    vendored: _Sequence[_Distribution]
    facts: object
    out: _Path


def _build_plan_record(inputs: _BuildPlanInputs) -> _BuildPlan:
    """Close the validated facts into the build plan record."""
    project = inputs.project
    config = project.config
    plugin = project.plugin
    version = config.version
    resolution = _resolve_runtime(project.root)
    prefix = f"{plugin}.{VENDOR_PACKAGE}"
    return _BuildPlan(
        project=project,
        report=inputs.report,
        web_outcome=inputs.web_outcome,
        vendored=inputs.vendored,
        plugin=plugin,
        version=version,
        archive=inputs.out / f"{plugin}-{version}.zip",
        resolution=resolution,
        runtime=resolution.installed or _runtime_version(),
        prefix=prefix,
        roots=(_RUNTIME_PACKAGE, *_vendored_roots(inputs.vendored)),
        external=config.build.external_roots,
        facts=inputs.facts,
    )


def build_plan(root, out, web, run) -> _BuildPlan:
    """Validate the project and resolve the runtime, versions and archive."""
    from ._build import read_vendored

    project = _load_project(root)
    config = project.config
    plugin = project.plugin
    report, web_outcome = _build_report(
        project, plugin, project.root / plugin / "web", web, run
    )
    vendored = read_vendored(config.build.vendor)
    facts = _introspect(config)
    out = _Path(out) if out is not None else project.root / OUTPUT_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    inputs = _BuildPlanInputs(
        project=project,
        report=report,
        web_outcome=web_outcome,
        vendored=vendored,
        facts=facts,
        out=out,
    )
    return _build_plan_record(inputs)


def _introspect(config: _ProjectConfig):
    """Introspect the plugin's host artifacts, translating its error."""
    try:
        return _introspect_plugin(config)
    except _QgisSdkArtifactError as error:
        raise QgisSdkBuildError(str(error)) from error


def _write_build_artifacts(plan: _BuildPlan, staged: _Path, package: _Path):
    """Render metadata, stage runtime/vendored trees, write NOTICE and ZIP."""
    from ._build import imports_optional, plugin_sources
    from ._staging import stage_runtime, write_archive

    config = plan.project.config
    (staged / _METADATA_FILE).write_text(
        _render_metadata(config, plan.facts), encoding="utf-8", newline="\n"
    )
    stage_runtime(
        staged / VENDOR_PACKAGE,
        prefix=plan.prefix,
        include_http=imports_optional(plugin_sources(package), "http"),
    )
    records = _stage_vendored(
        staged / VENDOR_PACKAGE, plan.vendored, prefix=plan.prefix
    )
    (staged / VENDOR_PACKAGE / "NOTICE").write_text(
        _notice(
            plan.runtime, requirement=plan.resolution.requirement, vendored=records
        ),
        encoding="utf-8",
        newline="\n",
    )
    return write_archive(plan.archive, staged.parent, plan.plugin), records


def stage_build(plan: _BuildPlan):
    """Stage the plugin, runtime and vendored packages into the archive."""
    from ._build import entry_points, stage_plugin

    config = plan.project.config
    package = plan.project.root / plan.plugin
    with _tempfile.TemporaryDirectory(prefix="qgis-sdk-build-") as staging:
        staged = _Path(staging) / plan.plugin
        stage_plugin(
            package,
            staged,
            prefix=plan.prefix,
            roots=plan.roots,
            append=entry_points(
                config, runtime_package=f"{plan.prefix}.{_RUNTIME_PACKAGE}"
            ),
        )
        return _write_build_artifacts(plan, staged, package)
