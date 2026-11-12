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
from pathlib import Path

from qgis_sdk_tools.bundle import (
    OUTPUT_DIRECTORY,
    VENDOR_PACKAGE,
    QgisSdkBuildError,
    QgisSdkBuildRefusedError,
    WebOutcome,
    _build_web,
    _imports_optional,
    _plugin_sources,
    _read_vendored,
    _stage_plugin,
    _stage_runtime,
)
from qgis_sdk_tools.bundle.validate import check_web_assets
from qgis_sdk_tools.bundle.vendor import (
    RUNTIME_PACKAGE,
    notice,
    runtime_version,
    stage_vendored,
    vendored_roots,
)
from qgis_sdk_tools.check import CheckReport, check_project
from qgis_sdk_tools.devtools.dev import QgisSdkDevError, inspect_project


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_build_app_p1(_s):
    try:
        _s.project = inspect_project(_s.root)
    except QgisSdkDevError as error:
        _s.error = error
        raise QgisSdkBuildError(str(_s.error)) from _s.error
    _s.root = _s.project.root
    _s.config = _s.project.config
    _s.plugin = _s.project.plugin
    _s.package = _s.root / _s.plugin
    _s.assets = _s.package / "web"


def cc_build_app_p2(_s):
    if not {"desktop", "app"} & set(_s.config.hosts):
        # A server-only project has no application to start: its declarations are
        # hooks QGIS Server calls (decision-52 point 1).
        raise QgisSdkBuildError(
            f"`--target app` needs an application, but {_s.plugin} declares "
            f"hosts = [{', '.join(repr(host) for host in _s.config.hosts)}]; add "
            "`app` (or `desktop`) to `[tool.qgis-sdk] hosts`, or build the plugin "
            "ZIP QGIS Server loads"
        )

    _s.report = check_project(_s.root)
    _s.diagnostics = list(_s.report.diagnostics)


def cc_build_app_p3(_s):
    _s.vendored = _read_vendored(_s.config.build.vendor)
    _s.web_outcome: WebOutcome = "none"
    if _s.project.web is not None:
        if _s.web:
            _build_web(_s.project.web, _s.run)
            _s.web_outcome = "built"
        else:
            _s.web_outcome = "prebuilt"
        _s.diagnostics.extend(check_web_assets(_s.assets, _s.plugin))
    _s.diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))


def cc_build_app_p4(_s):
    from ._build_app import APP_SUFFIX

    _s.report = CheckReport(
        root=_s.root,
        diagnostics=tuple(_s.diagnostics),
        files_checked=_s.report.files_checked,
    )
    if not _s.report.ok:
        raise QgisSdkBuildRefusedError(_s.report.diagnostics)

    _s.version = _s.config.version
    _s.out = Path(_s.out) if _s.out is not None else _s.root / OUTPUT_DIRECTORY
    _s.out.mkdir(parents=True, exist_ok=True)
    _s.directory = _s.out / f"{_s.plugin}-{_s.version}{APP_SUFFIX}"
    if _s.directory.exists():
        shutil.rmtree(_s.directory)


def cc_build_app_p5(_s):
    from ._build_app import LAUNCHER_MODULE, launcher_source

    _s.directory.mkdir(parents=True)
    _s.runtime = runtime_version()
    _s.prefix = f"{_s.plugin}.{VENDOR_PACKAGE}"
    _s.roots = (RUNTIME_PACKAGE, *vendored_roots(_s.vendored))
    _s.staged = _s.directory / _s.plugin
    _stage_plugin(
        _s.package,
        _s.staged,
        prefix=_s.prefix,
        roots=_s.roots,
        append={f"{LAUNCHER_MODULE}.py": launcher_source(_s.config)},
    )


def cc_build_app_p6(_s):
    _stage_runtime(
        _s.staged / VENDOR_PACKAGE,
        prefix=_s.prefix,
        include_http=_imports_optional(_plugin_sources(_s.package), "http"),
    )
    _s.records = stage_vendored(
        _s.staged / VENDOR_PACKAGE, _s.vendored, prefix=_s.prefix
    )
    (_s.staged / VENDOR_PACKAGE / "NOTICE").write_text(
        notice(_s.runtime, requirement=None, vendored=_s.records),
        encoding="utf-8",
        newline="\n",
    )


def cc_build_app_p7(_s):
    from ._build_app import distribution_project

    (_s.directory / "pyproject.toml").write_text(
        distribution_project(_s.config, directory=_s.staged),
        encoding="utf-8",
        newline="\n",
    )
    _s.files = tuple(
        path.relative_to(_s.directory).as_posix()
        for path in sorted(_s.directory.rglob("*"))
        if path.is_file()
    )


def cc_build_app_p8(_s):

    return CcReturn(
        _build_app_facts11234567891011121314151617(
            config=_s.config,
            directory=_s.directory,
            files=_s.files,
            plugin=_s.plugin,
            records=_s.records,
            report=_s.report,
            runtime=_s.runtime,
            version=_s.version,
            web_outcome=_s.web_outcome,
        )
    )


CC_TEXT_1 = '''"""Starts __TITLE__; written by `qgis-sdk build --target app`.

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
CC_TEXT_2 = """# Generated by `qgis-sdk build --target app` from {source}/pyproject.toml.
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


def _build_app_facts11234567891011121314151617(**values):
    return _build_app_facts112345678910111213141516(
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


def _build_app_facts112345678910111213141516(**values):
    return _build_app_facts1123456789101112131415(
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


def _build_app_facts1123456789101112131415(**values):
    return _build_app_facts11234567891011121314(
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


def _build_app_facts11234567891011121314(**values):
    return _build_app_facts112345678910111213(
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


def _build_app_facts112345678910111213(**values):
    return _build_app_facts1123456789101112(
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


def _build_app_facts1123456789101112(**values):
    return _build_app_facts11234567891011(
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


def _build_app_facts11234567891011(**values):
    return _build_app_facts112345678910(
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


def _build_app_facts112345678910(**values):
    return _build_app_facts1123456789(
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


def _build_app_facts1123456789(**values):
    from ._build_app import build_app_facts112345678

    return build_app_facts112345678(
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
