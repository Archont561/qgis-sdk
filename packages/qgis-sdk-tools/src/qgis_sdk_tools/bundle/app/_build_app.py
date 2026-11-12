from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk_tools.bundle import (
    RunProcess,
    WebOutcome,
)
from qgis_sdk_tools.check import CheckReport
from qgis_sdk_tools.project import ProjectConfig

from ._build_app_state import (
    CC_TEXT_1,
    CC_TEXT_2,
    CcReturn,
    CcState,
    cc_build_app_p1,
    cc_build_app_p2,
    cc_build_app_p3,
    cc_build_app_p4,
    cc_build_app_p5,
    cc_build_app_p6,
    cc_build_app_p7,
    cc_build_app_p8,
)


def build_app_facts112345678(**values):
    return _build_app_facts11234567(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts11234567(**values):
    return _build_app_facts1123456(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts1123456(**values):
    return _build_app_facts112345(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts112345(**values):
    return _build_app_facts11234(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts11234(**values):
    return _build_app_facts1123(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts1123(**values):
    return _build_app_facts112(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts112(**values):
    return _build_app_facts11(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts11(**values):
    return _build_app_facts1(
        config=values["config"],
        directory=values["directory"],
        files=values["files"],
        plugin=values["plugin"],
        records=values["records"],
        report=values["report"],
        runtime=values["runtime"],
        version=values["version"],
        web_outcome=values["web_outcome"],
    )


def _build_app_facts1(**values):
    return AppBuildResult(
        directory=values["directory"],
        plugin=values["plugin"],
        version=values["version"],
        files=values["files"],
        launcher=script_name(values["plugin"]),
        report=values["report"],
        runtime_version=values["runtime"],
        web=values["web_outcome"],
        external=values["config"].build.external_roots,
        vendored=tuple(name for name, _version in values["records"]),
    )


APP_SUFFIX: Final = "-app"
LAUNCHER_MODULE: Final = "_launcher"
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
    _s = CcState(root=root, out=out, web=web, run=run)
    for _p in (
        cc_build_app_p1,
        cc_build_app_p2,
        cc_build_app_p3,
        cc_build_app_p4,
        cc_build_app_p5,
        cc_build_app_p6,
        cc_build_app_p7,
        cc_build_app_p8,
    ):
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


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


_LAUNCHER_TEMPLATE: Final = CC_TEXT_1


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


_PROJECT_TEMPLATE: Final = CC_TEXT_2
