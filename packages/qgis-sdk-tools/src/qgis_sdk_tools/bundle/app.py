"""``qgis-sdk build --target app``: an installable distribution of one application.

The plugin ZIP the default target writes is what QGIS's *Install from ZIP* reads:
a package QGIS imports, with ``classFactory`` or ``serverClassFactory`` at the
top. A standalone app has no such caller (decision-52 point 3) - the entry is a
process - so this target writes something else: a Python project that ``pip
install`` turns into a console script, with the runtime inside it under the same
vendoring rules as the ZIP.

In order:

1. ``check_project`` and the build-only web rules: the same diagnostics the ZIP
   build refuses on.
2. The web page, when the project has one and the caller asked for it.
3. The plugin package staged under ``dist/<plugin>-<version>-app/<plugin>/``,
   with the runtime at ``_vendor/qgis_sdk`` and every ``qgis_sdk`` import
   rewritten to it (:mod:`qgis_sdk_tools.bundle.vendor`), plus a generated
   ``_launcher.py``: the entry the console script calls, with the declared
   externals probed before the application is imported.
4. ``pyproject.toml``: ``[project.scripts]`` for the launcher, the package
   discovery the staged tree needs, and ``package-data`` for the runtime's own
   non-Python files (the Processing catalogue and the reference styles), spelled
   file by file so a wheel built anywhere carries them.

Nothing is installed here, and the source tree is never touched: the directory is
the input to ``pip install``, whether a user runs it or a build harness does.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk_tools.check import CheckReport, check_project
from qgis_sdk_tools.devtools.dev import QgisSdkDevError, inspect_project
from qgis_sdk_tools.project import ProjectConfig

from . import (
    OUTPUT_DIRECTORY,
    VENDOR_PACKAGE,
    QgisSdkBuildError,
    QgisSdkBuildRefusedError,
    RunProcess,
    WebOutcome,
    _build_web,
    _imports_optional,
    _plugin_sources,
    _read_vendored,
    _stage_plugin,
    _stage_runtime,
)
from .validate import check_web_assets
from .vendor import (
    RUNTIME_PACKAGE,
    notice,
    runtime_version,
    stage_vendored,
    vendored_roots,
)

__all__ = [
    "APP_SUFFIX",
    "LAUNCHER_MODULE",
    "AppBuildResult",
    "build_app",
]

#: The directory a build writes: ``dist/<plugin>-<version>-app``.
APP_SUFFIX: Final = "-app"
#: The generated entry module inside the staged package.
LAUNCHER_MODULE: Final = "_launcher"
#: The shortest Python the runtime supports, when its metadata cannot say.
DEFAULT_REQUIRES_PYTHON: Final = ">=3.11"


@dataclass(frozen=True, slots=True)
class AppBuildResult:
    """What the app target wrote, and the findings that did not stop it."""

    directory: Path
    plugin: str
    version: str
    files: tuple[str, ...]
    launcher: str
    report: CheckReport
    runtime_version: str
    web: WebOutcome
    external: tuple[str, ...]
    vendored: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "target": "app",
            "directory": str(self.directory),
            "plugin": self.plugin,
            "version": self.version,
            "launcher": self.launcher,
            "files": len(self.files),
            "runtime_version": self.runtime_version,
            "web": self.web,
            "external": list(self.external),
            "vendored": list(self.vendored),
            "report": self.report.to_json(),
        }


def build_app(
    root: Path,
    *,
    out: Path | None = None,
    web: bool = True,
    run: RunProcess,
) -> AppBuildResult:
    """Write ``dist/<plugin>-<version>-app`` for the project at ``root``.

    ``run`` executes the web build (``argv``, ``cwd`` -> exit code); the CLI
    passes its runtime's ``run_process``. The directory is replaced when it
    exists, so a second build is the same tree rather than a union with the
    first.
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
    if not {"desktop", "app"} & set(config.hosts):
        # A server-only project has no application to start: its declarations are
        # hooks QGIS Server calls (decision-52 point 1).
        raise QgisSdkBuildError(
            f"`--target app` needs an application, but {plugin} declares "
            f"hosts = [{', '.join(repr(host) for host in config.hosts)}]; add "
            "`app` (or `desktop`) to `[tool.qgis-sdk] hosts`, or build the plugin "
            "ZIP QGIS Server loads"
        )

    report = check_project(root)
    diagnostics = list(report.diagnostics)
    vendored = _read_vendored(config.build.vendor)
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

    version = config.version
    out = Path(out) if out is not None else root / OUTPUT_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    directory = out / f"{plugin}-{version}{APP_SUFFIX}"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    runtime = runtime_version()
    prefix = f"{plugin}.{VENDOR_PACKAGE}"
    roots = (RUNTIME_PACKAGE, *vendored_roots(vendored))
    staged = directory / plugin
    _stage_plugin(
        package,
        staged,
        prefix=prefix,
        roots=roots,
        append={f"{LAUNCHER_MODULE}.py": launcher_source(config)},
    )
    _stage_runtime(
        staged / VENDOR_PACKAGE,
        prefix=prefix,
        include_http=_imports_optional(_plugin_sources(package), "http"),
    )
    records = stage_vendored(staged / VENDOR_PACKAGE, vendored, prefix=prefix)
    (staged / VENDOR_PACKAGE / "NOTICE").write_text(
        notice(runtime, requirement=None, vendored=records),
        encoding="utf-8",
        newline="\n",
    )
    (directory / "pyproject.toml").write_text(
        distribution_project(config, directory=staged),
        encoding="utf-8",
        newline="\n",
    )
    files = tuple(
        path.relative_to(directory).as_posix()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    )
    return AppBuildResult(
        directory=directory,
        plugin=plugin,
        version=version,
        files=files,
        launcher=script_name(plugin),
        report=report,
        runtime_version=runtime,
        web=web_outcome,
        external=config.build.external_roots,
        vendored=tuple(name for name, _version in records),
    )


def script_name(plugin: str) -> str:
    """The console script a user types: the package name with dashes."""
    return plugin.replace("_", "-")


def launcher_source(config: ProjectConfig) -> str:
    """``<plugin>/_launcher.py``: the generated entry the console script calls.

    The application comes from ``[tool.qgis-sdk] plugin``, so the launcher starts
    exactly what ``describe``, ``dev`` and the ZIP build read, and the flags are
    ``qgis_sdk.app``'s. Declared externals are imported before the application
    is, so a missing one is one message with the install command rather than a
    traceback from inside the plugin (decision-50 point 1).
    """
    module, _, attribute = config.spec.partition(":")
    declarations = "".join(
        f"    ({item.import_name!r}, {item.install_requirement!r}, "
        f"{item.reason or ''!r}),\n"
        for item in config.build.external
    )
    return (
        _LAUNCHER_TEMPLATE.replace("__TITLE__", config.description)
        .replace("__MODULE__", repr(module))
        .replace("__ATTRIBUTE__", repr(attribute))
        .replace("__EXTERNALS__", f"(\n{declarations})")
    )


#: The generated launcher. ``qgis_sdk`` is rewritten to the vendored path by
#: :func:`_stage_plugin`, exactly like the plugin's own modules.
_LAUNCHER_TEMPLATE: Final = '''"""Starts __TITLE__; written by `qgis-sdk build --target app`.

The application is the one `[tool.qgis-sdk] plugin` names, and the flags are
`qgis_sdk.app`'s: `--headless`, `--once`, `--grace`, `--title`, and everything
after `--` goes to the toolkit. This module is generated into the staged copy -
the project's own sources are never edited.
"""

from __future__ import annotations

import importlib
import sys

from qgis_sdk.app import main as run_app

#: (import name, pip requirement, why) for everything the project declares.
_EXTERNALS = __EXTERNALS__


def _missing_externals() -> list[str]:
    """The declared externals this interpreter cannot import, with the fix."""
    missing: list[str] = []
    for name, requirement, reason in _EXTERNALS:
        try:
            importlib.import_module(name)
        except ImportError:
            why = f" ({reason})" if reason else ""
            missing.append(f"{name}{why} is missing: pip install {requirement}")
    return missing


def main(argv=None) -> int:
    """Run the application; the console script calls this."""
    missing = _missing_externals()
    if missing:
        for line in missing:
            print(f"qgis-sdk app: {line}", file=sys.stderr)
        return 3
    application = getattr(importlib.import_module(__MODULE__), __ATTRIBUTE__)
    return run_app(application, argv)


if __name__ == "__main__":
    raise SystemExit(main())
'''


def distribution_project(config: ProjectConfig, *, directory: Path) -> str:
    """The ``pyproject.toml`` that makes the staged tree installable.

    Package data is spelled out from the staged tree - the runtime carries a
    Processing catalogue and three reference styles, and the plugin may carry its
    own - because a wheel built where no sdist manifest exists would otherwise
    drop them.
    """
    plugin = config.plugin
    return _PROJECT_TEMPLATE.format(
        source=config.root.as_posix(),
        name=script_name(plugin),
        version=config.version,
        description=_one_line(config.description),
        requires_python=requires_python(),
        script=script_name(plugin),
        plugin=plugin,
        package_data=package_data(directory, plugin=plugin),
    )


def package_data(directory: Path, *, plugin: str) -> str:
    """``[tool.setuptools.package-data]`` for the non-Python files that ship.

    One entry per package that has any, keyed by the *dotted* package name
    (``<plugin>._vendor.qgis_sdk.resources``) with each file's path relative to
    it, so a data directory that is not a package still ships. setuptools reads
    the table from the staged tree, so nothing depends on ``MANIFEST.in``
    surviving a wheel build.
    """
    entries: dict[str, list[str]] = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix == ".py":
            continue
        package = _owning_package(path.parent, stop=directory)
        if package is None:
            continue
        relative = package.relative_to(directory).as_posix()
        name = plugin if relative == "." else f"{plugin}.{relative.replace('/', '.')}"
        # A pattern may name a subdirectory: the runtime keeps its reference
        # styles in `resources/styles`, which is data inside `resources`.
        entries.setdefault(name, []).append(path.relative_to(package).as_posix())
    return "\n".join(
        f'"{package}" = [{", ".join(f"{name!r}" for name in names)}]'
        for package, names in sorted(entries.items())
    )


def _owning_package(start: Path, *, stop: Path) -> Path | None:
    """The nearest directory at or above ``start`` that is an importable package."""
    current = start
    while True:
        if (current / "__init__.py").is_file():
            return current
        if current == stop:
            return None
        current = current.parent


def requires_python() -> str:
    """The runtime's ``Requires-Python``, or the floor this kit is tested at."""
    from importlib import metadata

    try:
        declared = metadata.metadata("qgis-sdk-runtime").get("Requires-Python")
    except metadata.PackageNotFoundError:
        return DEFAULT_REQUIRES_PYTHON
    return declared or DEFAULT_REQUIRES_PYTHON


def _one_line(text: str) -> str:
    """A description as one line: a TOML string is a value, not a paragraph."""
    return " ".join(text.split())


_PROJECT_TEMPLATE: Final = """# Generated by `qgis-sdk build --target app` from {source}/pyproject.toml.
# Install it with `pip install .` (or `pip install --user .`), then run `{script}`.
# The runtime is vendored inside the package, so this distribution has no
# runtime dependency; the externals the project declares are probed by the
# launcher and are never installed by pip on its own.
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "{version}"
description = "{description}"
requires-python = "{requires_python}"
dependencies = []

[project.scripts]
{script} = "{plugin}._launcher:main"

[tool.setuptools.packages.find]
include = ["{plugin}*"]
namespaces = false

[tool.setuptools.package-data]
{package_data}
"""
