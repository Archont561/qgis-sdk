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

import ast
import os
import shutil
import stat
import tempfile
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.artifacts import (
    METADATA_FILE,
    QgisSdkArtifactError,
    class_factory_source,
    introspect_plugin,
    render_metadata,
)
from qgis_sdk_tools.check import CheckReport, Diagnostic, check_project
from qgis_sdk_tools.check.versions import resolve_runtime
from qgis_sdk_tools.devtools.dev import QgisSdkDevError, inspect_project
from qgis_sdk_tools.devtools.testrun import package_manager_for
from qgis_sdk_tools.distributions import (
    Distribution,
    QGisSdkDistributionError,
    read_distribution,
)
from qgis_sdk_tools.paths import walk_files
from qgis_sdk_tools.project import ProjectConfig
from qgis_sdk_tools.scaffold.web import script_command

from .validate import check_web_assets
from .vendor import (
    RUNTIME_PACKAGE,
    notice,
    rewrite_imports,
    runtime_files,
    runtime_source,
    runtime_version,
    stage_vendored,
    vendored_roots,
)

__all__ = [
    "VENDOR_PACKAGE",
    "BuildResult",
    "QgisSdkBuildError",
    "QgisSdkBuildRefusedError",
    "build_plugin",
    "rewrite_imports",
]

#: The plugin-private package the runtime copy lives in.
VENDOR_PACKAGE: Final = "_vendor"
OUTPUT_DIRECTORY: Final = "dist"
#: Never part of a built plugin, wherever they sit inside the package.
EXCLUDED_DIRECTORIES: Final = frozenset(
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
EXCLUDED_SUFFIXES: Final = frozenset({".pyc", ".pyo"})
EXCLUDED_FILES: Final = frozenset({".DS_Store"})
ZIP_EPOCH: Final = (1980, 1, 1, 0, 0, 0)

RunProcess = Callable[[Sequence[str], Path], int]
WebOutcome = Literal["none", "built", "prebuilt"]


class QgisSdkBuildError(QgisSdkError):
    """The build cannot run: not a project, a web build failed, no interpreter."""


class QgisSdkBuildRefusedError(QgisSdkBuildError):
    """The project has findings QGIS would not forgive; nothing was written."""

    def __init__(self, diagnostics: Sequence[Diagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        errors = sum(1 for d in self.diagnostics if d.severity == "error")
        super().__init__(
            f"build refused: {errors} error{'s' if errors != 1 else ''}; "
            "fix them and build again"
        )


@dataclass(frozen=True, slots=True)
class BuildResult:
    """What was built, and the findings that did not stop it."""

    archive: Path
    plugin: str
    version: str
    files: tuple[str, ...]
    report: CheckReport
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


@dataclass(frozen=True, slots=True)
class _BuildPlan:
    """Everything staging and the final result need, resolved once."""

    project: object
    report: CheckReport
    web_outcome: WebOutcome
    vendored: Sequence[Distribution]
    plugin: str
    version: str
    archive: Path
    resolution: object
    runtime: str
    prefix: str
    roots: tuple[str, ...]
    external: Sequence[str]
    facts: object


def _load_project(root: Path):
    """Read the project, translating a dev error into a build error."""
    try:
        return inspect_project(root)
    except QgisSdkDevError as error:
        raise QgisSdkBuildError(str(error)) from error


def _build_report(project, plugin, assets, web, run) -> tuple[CheckReport, WebOutcome]:
    """Run ``check`` plus the build-only rules; refuse on any error."""
    report = check_project(project.root)
    diagnostics = list(report.diagnostics)
    web_outcome: WebOutcome = "none"
    if project.web is not None:
        if web:
            _build_web(project.web, run)
            web_outcome = "built"
        else:
            web_outcome = "prebuilt"
        diagnostics.extend(check_web_assets(assets, plugin))
    diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))
    report = CheckReport(
        root=project.root,
        diagnostics=tuple(diagnostics),
        files_checked=report.files_checked,
    )
    if not report.ok:
        raise QgisSdkBuildRefusedError(report.diagnostics)
    return report, web_outcome


def _build_plan(root, out, web, run) -> _BuildPlan:
    """Validate the project and resolve the runtime, versions and archive."""
    project = _load_project(root)
    config = project.config
    plugin = project.plugin
    report, web_outcome = _build_report(
        project, plugin, project.root / plugin / "web", web, run
    )
    vendored = _read_vendored(config.build.vendor)
    facts = _introspect(config)
    version = config.version
    out = Path(out) if out is not None else project.root / OUTPUT_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    resolution = resolve_runtime(project.root)
    prefix = f"{plugin}.{VENDOR_PACKAGE}"
    return _BuildPlan(
        project=project,
        report=report,
        web_outcome=web_outcome,
        vendored=vendored,
        plugin=plugin,
        version=version,
        archive=out / f"{plugin}-{version}.zip",
        resolution=resolution,
        runtime=resolution.installed or runtime_version(),
        prefix=prefix,
        roots=(RUNTIME_PACKAGE, *vendored_roots(vendored)),
        external=config.build.external_roots,
        facts=facts,
    )


def _introspect(config: ProjectConfig):
    """Introspect the plugin's host artifacts, translating its error."""
    try:
        return introspect_plugin(config)
    except QgisSdkArtifactError as error:
        raise QgisSdkBuildError(str(error)) from error


def _write_build_artifacts(plan: _BuildPlan, staged: Path, package: Path):
    """Render metadata, stage runtime/vendored trees, write NOTICE and ZIP."""
    config = plan.project.config
    (staged / METADATA_FILE).write_text(
        render_metadata(config, plan.facts), encoding="utf-8", newline="\n"
    )
    _stage_runtime(
        staged / VENDOR_PACKAGE,
        prefix=plan.prefix,
        include_http=_imports_optional(_plugin_sources(package), "http"),
    )
    records = stage_vendored(staged / VENDOR_PACKAGE, plan.vendored, prefix=plan.prefix)
    (staged / VENDOR_PACKAGE / "NOTICE").write_text(
        notice(plan.runtime, requirement=plan.resolution.requirement, vendored=records),
        encoding="utf-8",
        newline="\n",
    )
    return _write_archive(plan.archive, staged.parent, plan.plugin), records


def _stage_build(plan: _BuildPlan):
    """Stage the plugin, runtime and vendored packages into the archive."""
    config = plan.project.config
    package = plan.project.root / plan.plugin
    with tempfile.TemporaryDirectory(prefix="qgis-sdk-build-") as staging:
        staged = Path(staging) / plan.plugin
        _stage_plugin(
            package,
            staged,
            prefix=plan.prefix,
            roots=plan.roots,
            append=_entry_points(
                config, runtime_package=f"{plan.prefix}.{RUNTIME_PACKAGE}"
            ),
        )
        return _write_build_artifacts(plan, staged, package)


def build_plugin(
    root: Path,
    *,
    out: Path | None = None,
    web: bool = True,
    run: RunProcess,
) -> BuildResult:
    """Build ``dist/<plugin>-<version>.zip`` (or into ``out``) for the project at ``root``.

    ``run`` executes the web build (``argv``, ``cwd`` -> exit code); the CLI
    passes its runtime's ``run_process``. ``web=False`` skips it and ships
    whatever is already under ``<plugin>/web``.
    """
    plan = _build_plan(root, out, web, run)
    files, records = _stage_build(plan)
    return _build_result(plan, files, records)


def _build_result(plan, files, records):
    return BuildResult(
        archive=plan.archive,
        plugin=plan.plugin,
        version=plan.version,
        files=files,
        report=plan.report,
        runtime_version=plan.runtime,
        web=plan.web_outcome,
        external=plan.external,
        runtime_requirement=plan.resolution.requirement,
        vendored=tuple(name for name, _version in records),
    )


def _read_vendored(names: Sequence[str]) -> tuple[Distribution, ...]:
    """The declared distributions, read from this interpreter's environment.

    ``check_project`` already refused a missing (``DEP004``) or compiled
    (``DEP003``) one, so a failure here is a race, not a user error, and is
    reported as the build failing rather than as a finding.
    """
    declared: list[Distribution] = []
    for name in names:
        try:
            declared.append(read_distribution(name))
        except QGisSdkDistributionError as error:
            raise QgisSdkBuildError(str(error)) from error
    return tuple(declared)


def _plugin_sources(package: Path) -> list[Path]:
    """The plugin's own ``.py`` files, excluding what the archive excludes."""
    return list(walk_files(package, skip=EXCLUDED_DIRECTORIES, suffix=".py"))


def _qualified_import(node: ast.Import, qualified: str, module: str) -> bool:
    """Whether one ``import`` names the optional module or a child of it."""
    return any(
        alias.name == qualified or alias.name.startswith(qualified + ".")
        for alias in node.names
    )


def _qualified_import_from(node: ast.ImportFrom, qualified: str, module: str) -> bool:
    """Whether one ``from`` import names the optional module or the package."""
    if node.level:
        return False
    if node.module == qualified or (node.module or "").startswith(qualified + "."):
        return True
    return node.module == "qgis_sdk" and any(
        alias.name == module for alias in node.names
    )


_IMPORT_CHECKS: Final[dict[type, Callable[[object, str, str], bool]]] = {
    ast.Import: _qualified_import,
    ast.ImportFrom: _qualified_import_from,
}


def _imports_optional(sources: Sequence[Path], module: str) -> bool:
    """Include an optional listener only for an explicit static import."""
    qualified = f"qgis_sdk.{module}"
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            check = _IMPORT_CHECKS.get(type(node))
            if check is not None and check(node, qualified, module):
                return True
    return False


def _build_web(web: Path, run: RunProcess) -> None:
    manager = package_manager_for(web)
    if not (web / "node_modules").is_dir():
        raise QgisSdkBuildError(
            f"web/node_modules is missing; run `{manager} install` in web/ first "
            "(qgis-sdk never installs on your behalf), or build the page yourself "
            "and pass --no-web"
        )
    argv = script_command(manager, "build")  # type: ignore[arg-type]
    code = run(argv, web)
    if code != 0:
        raise QgisSdkBuildError(
            f"web build failed: `{' '.join(argv)}` in {web} exited with {code}"
        )


def _entry_points(config: ProjectConfig, *, runtime_package: str) -> dict[str, str]:
    """What ``build`` appends to ``<plugin>/__init__.py``, per declared host.

    A Desktop plugin keeps an empty ``__init__.py`` in the source tree and gets
    its ``classFactory`` here (decision-43). A server plugin cannot: QGIS Server
    imports ``serverClassFactory`` from the package itself, so the source already
    carries it and ``build`` only writes ``server=True`` into ``metadata.txt``.
    A project that declares both hosts gets both lines and is loaded by each
    host through its own entry.
    """
    if "desktop" not in config.hosts:
        return {}
    return {
        "__init__.py": class_factory_source(
            config, runtime_package=runtime_package, by="qgis-sdk build"
        )
    }


@dataclass(frozen=True, slots=True)
class _StageFiles:
    """The shared state one plugin package's file staging needs."""

    staged: Path
    package: Path
    prefix: str
    roots: Sequence[str]
    extra: dict[str, str]


def _stage_source_file(source: Path, files: _StageFiles) -> None:
    """Copy one source file, rewriting Python imports and appending host text."""
    relative = source.parent.relative_to(files.package)
    target = files.staged / relative / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix != ".py":
        shutil.copyfile(source, target)
        return
    text = source.read_text(encoding="utf-8")
    if not relative.parts and source.name in files.extra:
        body = text.rstrip("\n")
        text = (body + "\n\n\n" if body else "") + files.extra.pop(source.name)
    target.write_text(
        rewrite_imports(text, prefix=files.prefix, roots=files.roots),
        encoding="utf-8",
        newline="\n",
    )


def _stage_plugin(
    package: Path,
    staged: Path,
    *,
    prefix: str,
    roots: Sequence[str] = (RUNTIME_PACKAGE,),
    append: Mapping[str, str] | None = None,
) -> None:
    """Copy the plugin package, filtered, rewriting its ``qgis_sdk`` imports.

    ``append`` adds text to named files (``__init__.py`` gets the generated
    ``classFactory``) before the rewrite, so a vendored import path applies
    to the generated lines too. The source tree is never touched.
    """
    extra = dict(append or {})
    staged.mkdir(parents=True, exist_ok=True)
    for source in walk_files(package, skip=EXCLUDED_DIRECTORIES):
        if source.suffix in EXCLUDED_SUFFIXES or source.name in EXCLUDED_FILES:
            continue
        _stage_source_file(source, _StageFiles(staged, package, prefix, roots, extra))
    for filename, text in extra.items():  # a package without the file at all
        (staged / filename).write_text(
            rewrite_imports(text, prefix=prefix, roots=roots),
            encoding="utf-8",
            newline="\n",
        )


def _stage_runtime(vendor: Path, *, prefix: str, include_http: bool) -> None:
    """Copy the runtime under ``vendor/qgis_sdk`` with its imports rewritten."""
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "__init__.py").write_text(
        '"""Runtime shipped with this plugin by `qgis-sdk build`; see NOTICE."""\n',
        encoding="utf-8",
        newline="\n",
    )
    source_root = runtime_source()
    for relative in runtime_files():
        if relative.parts[0] == "http" and not include_http:
            continue
        source = source_root / relative
        target = vendor / RUNTIME_PACKAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".py":
            target.write_text(
                rewrite_imports(source.read_text(encoding="utf-8"), prefix=prefix),
                encoding="utf-8",
                newline="\n",
            )
        else:
            shutil.copyfile(source, target)


def _write_archive(archive: Path, staging: Path, plugin: str) -> tuple[str, ...]:
    """A deterministic ZIP: sorted entries, fixed timestamps, normalised modes."""
    date_time = _timestamp()
    # Sorted by the archive name, not the Path: Windows compares paths
    # case-insensitively, and the order must be the same on every platform.
    entries = sorted(
        (path.relative_to(staging).as_posix(), path)
        for path in (staging / plugin).rglob("*")
        if path.is_file()
    )
    names: list[str] = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, path in entries:
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # unix, so the mode below is honoured
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zf.writestr(info, path.read_bytes())
            names.append(name)
    return tuple(names)


def _timestamp() -> tuple[int, int, int, int, int, int]:
    """``SOURCE_DATE_EPOCH`` when set (reproducible-builds convention), else 1980."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return ZIP_EPOCH
    moment = time.gmtime(int(epoch))
    return (
        max(moment.tm_year, 1980),
        moment.tm_mon,
        moment.tm_mday,
        moment.tm_hour,
        moment.tm_min,
        moment.tm_sec,
    )
