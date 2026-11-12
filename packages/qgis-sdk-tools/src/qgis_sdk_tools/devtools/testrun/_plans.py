"""One planner per target: build the process for ``pure``, ``qgis``, and the rest."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from qgis_sdk.environment import TEST_TARGET_ENV as TARGET_ENV

from qgis_sdk_tools.scaffold.web import script_command

from ..installs import QgisInstall, sdk_import_paths
from ._constants import (
    DESKTOP_PROBE,
    LOCKFILES,
    PLUGIN,
    PROBE_NAME,
    PROFILE_NAME,
    REQUEST_ENV,
    REQUEST_NAME,
    SELECTION,
)
from ._types import QgisSdkTestRunError, TestFacts, TestPlan

__all__ = ["package_manager_for", "pytest_args", "target_planners", "validate_plan"]


def validate_plan(root: Path, target: str, values) -> None:
    """Refuse a bad root, target or missing native prerequisite by name."""
    if not root.is_dir():
        raise QgisSdkTestRunError(f"{root} is not a directory; give a project root")
    if target not in ("pure", "qgis", "desktop", "server", "web"):
        raise QgisSdkTestRunError(
            f"unknown target {target!r}; choose one of pure, qgis, desktop, server, web"
        )
    if target in ("qgis", "server", "desktop") and values.install is None:
        raise QgisSdkTestRunError(f"target {target} needs a QGIS install")
    if target == "desktop" and values.workspace is None:
        raise QgisSdkTestRunError("target desktop needs a workspace directory")


def pytest_args(target: str, pytest_args: Sequence[str]) -> tuple[str, ...]:
    return ("-p", PLUGIN, "-m", SELECTION[target], *pytest_args)


def package_manager_for(web: Path) -> str:
    """The manager a ``web/`` directory's lockfile names; npm when none does."""
    for lockfile, manager in LOCKFILES:
        if (web / lockfile).is_file():
            return manager
    return "npm"


def target_planners() -> dict[str, Callable[[TestFacts], TestPlan]]:
    return {
        "web": _web_plan,
        "pure": _pure_plan,
        "qgis": _qgis_plan,
        "server": _server_plan,
        "desktop": _desktop_plan,
    }


def _pure_plan(facts: TestFacts) -> TestPlan:
    """The pure target runs in this interpreter with native imports refused."""
    argv = (sys.executable, "-m", "pytest", *pytest_args("pure", facts.args))
    return TestPlan(
        target="pure",
        argv=argv,
        cwd=facts.root,
        env={**facts.env, TARGET_ENV: "pure"},
        notes=("target pure: this interpreter, native imports refused",),
    )


def _web_plan(facts: TestFacts) -> TestPlan:
    return _plan_web(facts.root, facts.args, facts.env)


def _qgis_plan(facts: TestFacts) -> TestPlan:
    return _plan_qgis(facts.root, facts.args, facts.env, facts.install, facts.headless)


def _server_plan(facts: TestFacts) -> TestPlan:
    return _plan_server(facts.root, facts.args, facts.env, facts.install)


def _desktop_plan(facts: TestFacts) -> TestPlan:
    return _plan_desktop(facts)


def _plan_qgis(
    root: Path,
    args: Sequence[str],
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
        argv=(str(install.python), "-m", "pytest", *pytest_args("qgis", args)),
        cwd=root,
        env=process_env,
        notes=(
            (
                f"target qgis: QGIS {install.prefix} ({install.source}), "
                f"python {install.python}, {'offscreen' if headless else 'on screen'}"
            ),
        ),
    )


def _plan_server(
    root: Path,
    args: Sequence[str],
    env: Mapping[str, str],
    install: QgisInstall,
) -> TestPlan:
    """The install's interpreter, headless, with QGIS Server bindings.

    Whether ``qgis.server`` is there is answered by the process that will run
    the tests - the plugin refuses the session when it is missing, naming the
    build - because a plan cannot know which interpreter a prefix resolves to
    without starting it.
    """
    if install.python is None:
        raise QgisSdkTestRunError(
            f"{install.prefix} has no Python interpreter (bin/python, bin/python3 "
            "or python.exe); QGIS Server bindings only import into the "
            "interpreter they were built for, so this install cannot run the "
            "server target"
        )
    process_env = install.environment(
        env, extra_paths=sdk_import_paths(), headless=True
    )
    process_env[TARGET_ENV] = "server"
    return _server_plan_facts(install, process_env, args, root)


def _server_plan_facts(
    install: QgisInstall,
    process_env: dict[str, str],
    args: Sequence[str],
    root: Path,
) -> TestPlan:
    return TestPlan(
        target="server",
        argv=(
            str(install.python),
            "-m",
            "pytest",
            *pytest_args("server", args),
        ),
        cwd=root,
        env=process_env,
        notes=(
            (
                f"target server: QGIS {install.prefix} ({install.source}), "
                f"python {install.python}, offscreen; the tests marked server "
                "need a QGIS built with WITH_SERVER=ON and its bindings"
            ),
        ),
    )


def _desktop_argv(
    install: QgisInstall, workspace: Path, probe: Path
) -> tuple[str, ...]:
    """The QGIS Desktop invocation with its isolated profile and probe."""
    return (
        str(install.executable),
        "--noplugins",
        "--profiles-path",
        str(workspace / "profiles"),
        "--profile",
        PROFILE_NAME,
        "--code",
        str(probe),
    )


def _desktop_notes(
    install: QgisInstall, workspace: Path, headless: bool
) -> tuple[str, ...]:
    """The one console line the desktop target prints."""
    return (
        (
            f"target desktop: QGIS Desktop {install.executable} "
            f"({install.source}), profile {workspace / 'profiles'}, "
            f"{'offscreen' if headless else 'on screen'}"
        ),
    )


def _desktop_environment(
    facts: TestFacts, install: QgisInstall, request: Path, plugin_path: Path
) -> dict[str, str]:
    """Build the QGIS process environment and point it at the written request."""
    process_env = install.environment(
        facts.env,
        extra_paths=(facts.root, *sdk_import_paths()),
        headless=facts.headless,
        desktop=True,
    )
    process_env[TARGET_ENV] = "desktop"
    process_env[REQUEST_ENV] = str(request)
    process_env["QGIS_PLUGINPATH"] = str(plugin_path)
    return process_env


def _desktop_probe(workspace: Path, root: Path, args: Sequence[str]) -> Path:
    """Write the request and the probe the desktop target runs; return the request."""
    request = workspace / REQUEST_NAME
    request.write_text(
        json.dumps({"cwd": str(root), "args": list(pytest_args("desktop", args))}),
        encoding="utf-8",
    )
    probe = workspace / PROBE_NAME
    probe.write_text(DESKTOP_PROBE, encoding="utf-8", newline="\n")
    return request


def _plan_desktop(facts: TestFacts) -> TestPlan:
    """The real Desktop GUI, with a generated host and an isolated profile."""
    install = facts.install
    if install.executable is None:
        raise QgisSdkTestRunError(
            f"{install.prefix} has no QGIS Desktop binary (bin/qgis or "
            "bin/qgis-bin.exe); install QGIS Desktop there or run "
            "`qgis-sdk test --target qgis` for tests that need no Desktop"
        )
    workspace = Path(facts.workspace)
    request = _desktop_probe(workspace, facts.root, facts.args)
    plugin_path = _stage_host_for_tests(facts.root)
    process_env = _desktop_environment(facts, install, request, plugin_path)
    return TestPlan(
        target="desktop",
        argv=_desktop_argv(install, workspace, workspace / PROBE_NAME),
        cwd=facts.root,
        env=process_env,
        notes=_desktop_notes(install, workspace, facts.headless),
        workspace=workspace,
    )


def _stage_host_for_tests(root: Path) -> Path:
    """The generated host package for ``QGIS_PLUGINPATH``; the root when there is none.

    A project without ``[tool.qgis-sdk] plugin`` still runs its desktop
    tests - they may not load the plugin by name, and ``check`` says why.
    """
    from ..dev import QgisSdkDevError, inspect_project, stage_host

    try:
        return stage_host(inspect_project(root))
    except QgisSdkDevError:
        return root


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
