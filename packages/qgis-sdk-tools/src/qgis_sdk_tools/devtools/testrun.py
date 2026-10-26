"""The plan behind ``qgis-sdk test``: one target, one process, pytest's own verdict.

The command is a thin runner (decision-8). It decides *where* pytest runs -
this interpreter, the QGIS install's interpreter, or inside the QGIS Desktop
binary - and *what* it selects, then forwards the user's arguments, output and
exit code untouched. Nothing is installed; a target whose runtime is missing
raises before anything runs, so a required gate never passes by skipping.

Targets:

``pure``
    this interpreter; tests not marked ``qgis``/``desktop``; native imports
    refused by the plugin's guard;
``qgis``
    the install's interpreter with PyQGIS importable; tests marked ``qgis``;
    ``qgis_app`` is a headless ``QgsApplication``;
``desktop``
    pytest inside the QGIS Desktop binary against a throwaway profile; tests
    marked ``desktop``; ``qgis_iface`` is the real interface, and the
    project's plugin is loadable by name through the same generated host
    package ``qgis-sdk dev`` stages (decision-43);
``web``
    the project's Vitest through the manager its lockfile names.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk.environment import TEST_TARGET_ENV as TARGET_ENV
from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.scaffold.web import script_command

from .installs import QgisInstall, sdk_import_paths, wants_headless

__all__ = [
    "PLUGIN",
    "PROFILE_NAME",
    "REQUEST_ENV",
    "TARGETS",
    "QgisSdkTestRunError",
    "TestPlan",
    "package_manager_for",
    "plan_tests",
]

PLUGIN: Final = "qgis_sdk_tools.pytest_plugin"
TARGETS: Final = ("pure", "qgis", "desktop", "web")
NATIVE_TARGETS: Final = frozenset({"qgis", "desktop"})
PROFILE_NAME: Final = "qgis-sdk-test"
REQUEST_ENV: Final = "QGIS_SDK_TEST_REQUEST"
PROBE_NAME: Final = "pytest-probe.py"
REQUEST_NAME: Final = "pytest-request.json"

SELECTION: Final = {
    "pure": "not qgis and not desktop",
    "qgis": "qgis",
    "desktop": "desktop",
}

LOCKFILES: Final = (
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("package-lock.json", "npm"),
)

#: Runs inside the Desktop binary (``qgis --code``). It reads its request from
#: a file because QGIS treats trailing arguments as project paths, and ends the
#: process itself because Desktop would otherwise sit in its event loop.
DESKTOP_PROBE: Final = '''"""Run pytest inside QGIS Desktop and exit with its verdict (qgis-sdk test)."""

import json
import os
import sys

request = json.loads(open(os.environ["QGIS_SDK_TEST_REQUEST"], encoding="utf-8").read())
# QGIS may have hooked the streams for its console; pytest talks to the terminal.
sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
os.chdir(request["cwd"])
sys.path.insert(0, request["cwd"])

try:
    import pytest
except ImportError as error:
    sys.stderr.write(
        "qgis-sdk test: pytest is not importable inside QGIS Desktop's Python "
        f"({sys.executable}): {error}\\n"
    )
    sys.stderr.flush()
    os._exit(4)

code = pytest.main(request["args"])
sys.stdout.flush()
sys.stderr.flush()
os._exit(int(code))
'''


class QgisSdkTestRunError(QgisSdkError):
    """The run cannot start: wrong target, no project, or the runtime is missing."""


@dataclass(frozen=True, slots=True)
class TestPlan:
    """What to run: the process, where, with which environment."""

    target: str
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    notes: tuple[str, ...]
    workspace: Path | None = None


def plan_tests(
    root: Path,
    target: str,
    pytest_args: Sequence[str],
    *,
    env: Mapping[str, str],
    install: QgisInstall | None = None,
    workspace: Path | None = None,
    python: str = sys.executable,
    platform: str = sys.platform,
) -> TestPlan:
    """Return the process for ``target`` at ``root``; raise when it cannot run.

    ``install`` is required for the native targets and ignored otherwise.
    ``workspace`` is the throwaway directory the ``desktop`` target writes its
    probe and profile into; the caller owns and removes it.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise QgisSdkTestRunError(f"{root} is not a directory; give a project root")
    if target not in TARGETS:
        raise QgisSdkTestRunError(
            f"unknown target {target!r}; choose one of {', '.join(TARGETS)}"
        )
    if target == "web":
        return _plan_web(root, pytest_args, env)
    if target == "pure":
        argv = (python, "-m", "pytest", *_pytest_args("pure", pytest_args))
        return TestPlan(
            target="pure",
            argv=argv,
            cwd=root,
            env={**env, TARGET_ENV: "pure"},
            notes=("target pure: this interpreter, native imports refused",),
        )
    if install is None:
        raise QgisSdkTestRunError(f"target {target} needs a QGIS install")
    headless = wants_headless(env, platform=platform)
    if target == "qgis":
        return _plan_qgis(root, pytest_args, env, install, headless)
    if workspace is None:
        raise QgisSdkTestRunError("target desktop needs a workspace directory")
    return _plan_desktop(root, pytest_args, env, install, headless, workspace)


def _pytest_args(target: str, pytest_args: Sequence[str]) -> tuple[str, ...]:
    return ("-p", PLUGIN, "-m", SELECTION[target], *pytest_args)


def _plan_qgis(
    root: Path,
    pytest_args: Sequence[str],
    env: Mapping[str, str],
    install: QgisInstall,
    headless: bool,
) -> TestPlan:
    if install.python is None:
        raise QgisSdkTestRunError(
            f"{install.prefix} has no Python interpreter (bin/python, bin/python3 "
            "or python.exe); PyQGIS only imports into the interpreter it was built "
            "for, so this install cannot run the qgis target"
        )
    process_env = install.environment(
        env, extra_paths=sdk_import_paths(), headless=headless
    )
    process_env[TARGET_ENV] = "qgis"
    return TestPlan(
        target="qgis",
        argv=(str(install.python), "-m", "pytest", *_pytest_args("qgis", pytest_args)),
        cwd=root,
        env=process_env,
        notes=(
            (
                f"target qgis: QGIS {install.prefix} ({install.source}), "
                f"python {install.python}, {'offscreen' if headless else 'on screen'}"
            ),
        ),
    )


def _plan_desktop(
    root: Path,
    pytest_args: Sequence[str],
    env: Mapping[str, str],
    install: QgisInstall,
    headless: bool,
    workspace: Path,
) -> TestPlan:
    if install.executable is None:
        raise QgisSdkTestRunError(
            f"{install.prefix} has no QGIS Desktop binary (bin/qgis or "
            "bin/qgis-bin.exe); install QGIS Desktop there or run "
            "`qgis-sdk test --target qgis` for tests that need no Desktop"
        )
    workspace = Path(workspace)
    request = workspace / REQUEST_NAME
    request.write_text(
        json.dumps(
            {"cwd": str(root), "args": list(_pytest_args("desktop", pytest_args))}
        ),
        encoding="utf-8",
    )
    probe = workspace / PROBE_NAME
    probe.write_text(DESKTOP_PROBE, encoding="utf-8", newline="\n")
    plugin_path = _stage_host_for_tests(root)
    process_env = install.environment(
        env, extra_paths=(root, *sdk_import_paths()), headless=headless, desktop=True
    )
    process_env[TARGET_ENV] = "desktop"
    process_env[REQUEST_ENV] = str(request)
    process_env["QGIS_PLUGINPATH"] = str(plugin_path)
    return TestPlan(
        target="desktop",
        argv=(
            str(install.executable),
            "--noplugins",
            "--profiles-path",
            str(workspace / "profiles"),
            "--profile",
            PROFILE_NAME,
            "--code",
            str(probe),
        ),
        cwd=root,
        env=process_env,
        notes=(
            (
                f"target desktop: QGIS Desktop {install.executable} "
                f"({install.source}), profile {workspace / 'profiles'}, "
                f"{'offscreen' if headless else 'on screen'}"
            ),
        ),
        workspace=workspace,
    )


def _stage_host_for_tests(root: Path) -> Path:
    """The generated host package for ``QGIS_PLUGINPATH``; the root when there is none.

    A project without ``[tool.qgis-sdk] plugin`` still runs its desktop
    tests - they may not load the plugin by name, and ``check`` says why.
    """
    from .dev import QgisSdkDevError, inspect_project, stage_host

    try:
        return stage_host(inspect_project(root))
    except QgisSdkDevError:
        return root


def package_manager_for(web: Path) -> str:
    """The manager a ``web/`` directory's lockfile names; npm when none does."""
    for lockfile, manager in LOCKFILES:
        if (web / lockfile).is_file():
            return manager
    return "npm"


def _plan_web(root: Path, args: Sequence[str], env: Mapping[str, str]) -> TestPlan:
    web = root / "web"
    if not (web / "package.json").is_file():
        raise QgisSdkTestRunError(
            f"{root} has no web/package.json, so there are no web tests to run; "
            "`qgis-sdk new --web vanilla|react` adds a web UI"
        )
    manager = package_manager_for(web)
    if not (web / "node_modules").is_dir():
        raise QgisSdkTestRunError(
            f"web/node_modules is missing; run `{manager} install` in web/ first "
            "(qgis-sdk never installs on your behalf)"
        )
    argv = list(script_command(manager, "test"))  # type: ignore[arg-type]
    if args:
        if manager == "npm":
            argv.append("--")
        argv.extend(args)
    return TestPlan(
        target="web",
        argv=tuple(argv),
        cwd=web,
        env=dict(env),
        notes=(f"target web: {manager} in web/",),
    )
