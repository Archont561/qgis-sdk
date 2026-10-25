"""``qgis-sdk build``: a validated, installable plugin ZIP (TASK-8, decision-8).

``build_plugin`` is the library the command calls. In order:

1. ``check_project`` plus the build-only rules in :mod:`.validate`; any
   error refuses the build with the same diagnostics ``check`` prints.
2. The web page, when the project has one: run the project's own build
   script (never install anything) or ship a page already built.
3. Stage the plugin package without caches, tests and tooling state, add
   the runtime under ``<plugin>/_vendor/qgis_sdk`` with imports rewritten
   (:mod:`.vendor`), and write a reproducible ZIP whose only root entry is
   the plugin directory - what QGIS's *Install from ZIP* expects.
"""

from __future__ import annotations

import configparser
import os
import shutil
import stat
import tempfile
import time
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.check import CheckReport, Diagnostic, check_project
from qgis_sdk_tools.devtools.dev import QgisSdkDevError, inspect_project
from qgis_sdk_tools.devtools.testrun import package_manager_for
from qgis_sdk_tools.scaffold.web import script_command

from .validate import (
    check_dependencies,
    check_entry_point,
    check_web_assets,
    external_dependencies,
)
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

    def to_json(self) -> dict[str, object]:
        return {
            "archive": str(self.archive),
            "plugin": self.plugin,
            "version": self.version,
            "files": len(self.files),
            "runtime_version": self.runtime_version,
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
    plugin = project.plugin
    package = root / plugin
    assets = package / "web"

    report = check_project(root)
    diagnostics = list(report.diagnostics)
    external, config_findings = external_dependencies(root)
    diagnostics.extend(config_findings)
    diagnostics.extend(check_entry_point(root, plugin))
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

    version = _metadata_version(package / "metadata.txt")
    out = Path(out) if out is not None else root / OUTPUT_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{plugin}-{version}.zip"
    runtime = runtime_version()
    with tempfile.TemporaryDirectory(prefix="qgis-sdk-build-") as staging:
        staged = Path(staging) / plugin
        _stage_plugin(package, staged, prefix=f"{plugin}.{VENDOR_PACKAGE}")
        _stage_runtime(staged / VENDOR_PACKAGE, prefix=f"{plugin}.{VENDOR_PACKAGE}")
        (staged / VENDOR_PACKAGE / "NOTICE").write_text(
            notice(runtime), encoding="utf-8", newline="\n"
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


def _metadata_version(metadata: Path) -> str:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # type: ignore[assignment]
    parser.read_string(metadata.read_text(encoding="utf-8"))
    return parser.get("general", "version").strip()


def _stage_plugin(package: Path, staged: Path, *, prefix: str) -> None:
    """Copy the plugin package, filtered, rewriting its ``qgis_sdk`` imports."""
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
                target.write_text(
                    rewrite_imports(source.read_text(encoding="utf-8"), prefix=prefix),
                    encoding="utf-8",
                    newline="\n",
                )
            else:
                shutil.copyfile(source, target)


def _stage_runtime(vendor: Path, *, prefix: str) -> None:
    """Copy the runtime under ``vendor/qgis_sdk`` with its imports rewritten."""
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "__init__.py").write_text(
        '"""Runtime shipped with this plugin by `qgis-sdk build`; see NOTICE."""\n',
        encoding="utf-8",
        newline="\n",
    )
    source_root = runtime_source()
    for relative in runtime_files():
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
    entries = sorted(path for path in (staging / plugin).rglob("*") if path.is_file())
    names: list[str] = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in entries:
            name = path.relative_to(staging).as_posix()
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
