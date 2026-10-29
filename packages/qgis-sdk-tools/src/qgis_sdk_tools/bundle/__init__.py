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
from qgis_sdk_tools.scaffold.web import script_command

from .validate import check_dependencies, check_web_assets, external_dependencies
from .vendor import (
    RUNTIME_PACKAGE,
    notice,
    rewrite_imports,
    runtime_files,
    runtime_source,
    runtime_version,
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
            "report": self.report.to_json(),
        }


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
    try:
        project = inspect_project(root)
    except QgisSdkDevError as error:
        raise QgisSdkBuildError(str(error)) from error
    root = project.root
    config = project.config
    plugin = project.plugin
    package = root / plugin
    assets = package / "web"

    report = check_project(root)
    diagnostics = list(report.diagnostics)
    external, config_findings = external_dependencies(root)
    diagnostics.extend(config_findings)
    diagnostics.extend(
        check_dependencies(root, plugin, _plugin_sources(package), external=external)
    )
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
        root=root, diagnostics=tuple(diagnostics), files_checked=report.files_checked
    )
    if not report.ok:
        raise QgisSdkBuildRefusedError(report.diagnostics)

    try:
        facts = introspect_plugin(config)
    except QgisSdkArtifactError as error:
        raise QgisSdkBuildError(str(error)) from error
    version = config.version
    out = Path(out) if out is not None else root / OUTPUT_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{plugin}-{version}.zip"
    resolution = resolve_runtime(root)
    runtime = resolution.installed or runtime_version()
    prefix = f"{plugin}.{VENDOR_PACKAGE}"
    with tempfile.TemporaryDirectory(prefix="qgis-sdk-build-") as staging:
        staged = Path(staging) / plugin
        _stage_plugin(
            package,
            staged,
            prefix=prefix,
            append={
                "__init__.py": class_factory_source(
                    config,
                    runtime_package=f"{prefix}.{RUNTIME_PACKAGE}",
                    by="qgis-sdk build",
                )
            },
        )
        (staged / METADATA_FILE).write_text(
            render_metadata(config, facts), encoding="utf-8", newline="\n"
        )
        _stage_runtime(
            staged / VENDOR_PACKAGE,
            prefix=prefix,
            include_http=_imports_optional(_plugin_sources(package), "http"),
        )
        (staged / VENDOR_PACKAGE / "NOTICE").write_text(
            notice(runtime, requirement=resolution.requirement),
            encoding="utf-8",
            newline="\n",
        )
        files = _write_archive(archive, Path(staging), plugin)
    return BuildResult(
        archive=archive,
        plugin=plugin,
        version=version,
        files=files,
        report=report,
        runtime_version=runtime,
        web=web_outcome,
        external=external,
        runtime_requirement=resolution.requirement,
    )


# -- steps ----------------------------------------------------------------------


def _plugin_sources(package: Path) -> list[Path]:
    """The plugin's own ``.py`` files, excluding what the archive excludes."""
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(package):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRECTORIES)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                files.append(Path(directory) / filename)
    return files


def _imports_optional(sources: Sequence[Path], module: str) -> bool:
    """Include an optional listener only for an explicit static import."""
    qualified = f"qgis_sdk.{module}"
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(
                    alias.name == qualified or alias.name.startswith(qualified + ".")
                    for alias in node.names
                ):
                    return True
            elif isinstance(node, ast.ImportFrom) and not node.level:
                if node.module == qualified or (node.module or "").startswith(
                    qualified + "."
                ):
                    return True
                if node.module == "qgis_sdk" and any(
                    alias.name == module for alias in node.names
                ):
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


def _stage_plugin(
    package: Path,
    staged: Path,
    *,
    prefix: str,
    append: Mapping[str, str] | None = None,
) -> None:
    """Copy the plugin package, filtered, rewriting its ``qgis_sdk`` imports.

    ``append`` adds text to named files (``__init__.py`` gets the generated
    ``classFactory``) before the rewrite, so a vendored import path applies
    to the generated lines too. The source tree is never touched.
    """
    extra = dict(append or {})
    for directory, dirnames, filenames in os.walk(package):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRECTORIES)
        relative = Path(directory).relative_to(package)
        (staged / relative).mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            source = Path(directory) / filename
            if source.suffix in EXCLUDED_SUFFIXES or filename in EXCLUDED_FILES:
                continue
            target = staged / relative / filename
            if source.suffix == ".py":
                text = source.read_text(encoding="utf-8")
                if relative == Path() and filename in extra:
                    body = text.rstrip("\n")
                    text = (body + "\n\n\n" if body else "") + extra.pop(filename)
                target.write_text(
                    rewrite_imports(text, prefix=prefix), encoding="utf-8", newline="\n"
                )
            else:
                shutil.copyfile(source, target)
    for filename, text in extra.items():  # a package without the file at all
        (staged / filename).write_text(
            rewrite_imports(text, prefix=prefix), encoding="utf-8", newline="\n"
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
