from __future__ import annotations

import ast as _ast
import shutil as _shutil
from collections.abc import Callable as _Callable
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path
from typing import Final as _Final

from qgis_sdk_tools.artifacts import (
    class_factory_source as _class_factory_source,
)
from qgis_sdk_tools.bundle.vendor import (
    RUNTIME_PACKAGE as _RUNTIME_PACKAGE,
)
from qgis_sdk_tools.bundle.vendor import (
    rewrite_imports,
)
from qgis_sdk_tools.devtools.testrun import package_manager_for as _package_manager_for
from qgis_sdk_tools.distributions import (
    Distribution as _Distribution,
)
from qgis_sdk_tools.distributions import (
    QGisSdkDistributionError as _QGisSdkDistributionError,
)
from qgis_sdk_tools.distributions import (
    read_distribution as _read_distribution,
)
from qgis_sdk_tools.paths import walk_files as _walk_files
from qgis_sdk_tools.project import ProjectConfig as _ProjectConfig
from qgis_sdk_tools.scaffold.web import script_command as _script_command

from ._errors import (
    EXCLUDED_DIRECTORIES,
    EXCLUDED_FILES,
    EXCLUDED_SUFFIXES,
    BuildResult,
    QgisSdkBuildError,
    RunProcess,
    build_plan,
    stage_build,
)


def build_plugin(
    root: _Path,
    *,
    out: _Path | None = None,
    web: bool = True,
    run: RunProcess,
) -> BuildResult:
    """Build ``dist/<plugin>-<version>.zip`` (or into ``out``) for the project at ``root``.

    ``run`` executes the web build (``argv``, ``cwd`` -> exit code); the CLI
    passes its runtime's ``run_process``. ``web=False`` skips it and ships
    whatever is already under ``<plugin>/web``.
    """
    plan = build_plan(root, out, web, run)
    files, records = stage_build(plan)
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


def read_vendored(names: _Sequence[str]) -> tuple[_Distribution, ...]:
    """The declared distributions, read from this interpreter's environment.

    ``check_project`` already refused a missing (``DEP004``) or compiled
    (``DEP003``) one, so a failure here is a race, not a user error, and is
    reported as the build failing rather than as a finding.
    """
    declared: list[_Distribution] = []
    for name in names:
        try:
            declared.append(_read_distribution(name))
        except _QGisSdkDistributionError as error:
            raise QgisSdkBuildError(str(error)) from error
    return tuple(declared)


def plugin_sources(package: _Path) -> list[_Path]:
    """The plugin's own ``.py`` files, excluding what the archive excludes."""
    return list(_walk_files(package, skip=EXCLUDED_DIRECTORIES, suffix=".py"))


def _qualified_import(node: _ast.Import, qualified: str, module: str) -> bool:
    """Whether one ``import`` names the optional module or a child of it."""
    return any(
        alias.name == qualified or alias.name.startswith(qualified + ".")
        for alias in node.names
    )


def _qualified_import_from(node: _ast.ImportFrom, qualified: str, module: str) -> bool:
    """Whether one ``from`` import names the optional module or the package."""
    if node.level:
        return False
    if node.module == qualified or (node.module or "").startswith(qualified + "."):
        return True
    return node.module == "qgis_sdk" and any(
        alias.name == module for alias in node.names
    )


_IMPORT_CHECKS: _Final[dict[type, _Callable[[object, str, str], bool]]] = {
    _ast.Import: _qualified_import,
    _ast.ImportFrom: _qualified_import_from,
}


def imports_optional(sources: _Sequence[_Path], module: str) -> bool:
    """Include an optional listener only for an explicit static import."""
    qualified = f"qgis_sdk.{module}"
    for source in sources:
        tree = _ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in _ast.walk(tree):
            check = _IMPORT_CHECKS.get(type(node))
            if check is not None and check(node, qualified, module):
                return True
    return False


def build_web(web: _Path, run: RunProcess) -> None:
    manager = _package_manager_for(web)
    if not (web / "node_modules").is_dir():
        raise QgisSdkBuildError(
            f"web/node_modules is missing; run `{manager} install` in web/ first "
            "(qgis-sdk never installs on your behalf), or build the page yourself "
            "and pass --no-web"
        )
    argv = _script_command(manager, "build")  # type: ignore[arg-type]
    code = run(argv, web)
    if code != 0:
        raise QgisSdkBuildError(
            f"web build failed: `{' '.join(argv)}` in {web} exited with {code}"
        )


def entry_points(config: _ProjectConfig, *, runtime_package: str) -> dict[str, str]:
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
        "__init__.py": _class_factory_source(
            config, runtime_package=runtime_package, by="qgis-sdk build"
        )
    }


@_dataclass(frozen=True, slots=True)
class _StageFiles:
    """The shared state one plugin package's file staging needs."""

    staged: _Path
    package: _Path
    prefix: str
    roots: _Sequence[str]
    extra: dict[str, str]


def _stage_source_file(source: _Path, files: _StageFiles) -> None:
    """Copy one source file, rewriting Python imports and appending host text."""
    relative = source.parent.relative_to(files.package)
    target = files.staged / relative / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix != ".py":
        _shutil.copyfile(source, target)
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


def stage_plugin(
    package: _Path,
    staged: _Path,
    *,
    prefix: str,
    roots: _Sequence[str] = (_RUNTIME_PACKAGE,),
    append: _Mapping[str, str] | None = None,
) -> None:
    """Copy the plugin package, filtered, rewriting its ``qgis_sdk`` imports.

    ``append`` adds text to named files (``__init__.py`` gets the generated
    ``classFactory``) before the rewrite, so a vendored import path applies
    to the generated lines too. The source tree is never touched.
    """
    extra = dict(append or {})
    staged.mkdir(parents=True, exist_ok=True)
    for source in _walk_files(package, skip=EXCLUDED_DIRECTORIES):
        if source.suffix in EXCLUDED_SUFFIXES or source.name in EXCLUDED_FILES:
            continue
        _stage_source_file(source, _StageFiles(staged, package, prefix, roots, extra))
    for filename, text in extra.items():  # a package without the file at all
        (staged / filename).write_text(
            rewrite_imports(text, prefix=prefix, roots=roots),
            encoding="utf-8",
            newline="\n",
        )
