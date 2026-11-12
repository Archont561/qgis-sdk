from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, Unpack

from qgis_sdk_tools.devtools.installs import (
    QgisInstall,
    sdk_import_paths,
    wants_headless,
)

from ._helpers import (
    STANDALONE_PROBE,
    WaitOptions1,
    WaitValues1,
    free_port,
)
from ._plans import (
    APP_PROBE_NAME,
    DESKTOP_PROBE_NAME,
    PROFILE_NAME,
    STANDALONE_PROBE_NAME,
    STATE_DIRECTORY,
    AppOptions,
    DevFacts,
    DevOptions,
    DevPlan,
    DevProject,
    QgisSdkDevError,
    dev_facts,
    plan_app_phase1,
    probe_env,
    reload_note,
    server_plan,
)


def _standalone_plan(facts: DevFacts) -> DevPlan:
    """A bare QgsApplication started by the install's interpreter."""
    install = facts.install
    if install.python is None:
        raise QgisSdkDevError(
            f"{install.prefix} has no Python interpreter, so it cannot run the "
            "standalone mode; use --mode desktop"
        )
    probe = facts.workspace / STANDALONE_PROBE_NAME
    probe.write_text(STANDALONE_PROBE, encoding="utf-8", newline="\n")
    process_env = probe_env(facts, headless=facts.headless)
    return DevPlan(
        mode=facts.mode,
        argv=(str(install.python), str(probe)),
        cwd=facts.project.root,
        env=process_env,
        notes=(
            (
                f"standalone: QgsApplication from {install.prefix} "
                f"({install.source}); no iface, no plugin lifecycle, no reload - "
                f"{facts.project.plugin} runs through the generated "
                f"{facts.host_root / facts.project.plugin} classFactory(None){facts.served}"
            ),
        ),
        profile=None,
    )


def _desktop_notes(
    facts: DevFacts, install: QgisInstall, profile: Path
) -> tuple[str, ...]:
    """The three console lines a desktop-mode run prints."""
    return (
        (
            f"desktop: {install.executable} ({install.source}), profile "
            f"{profile}, {facts.project.plugin} from {facts.project.root} through the "
            f"generated {facts.host_root / facts.project.plugin} on "
            f"QGIS_PLUGINPATH{facts.served}"
        ),
        reload_note(
            facts,
            "reload: on save of Python changes, the Reload button, "
            "or Ctrl+Shift+R in QGIS; quit QGIS to stop "
            "(a pyproject.toml change needs a new `qgis-sdk dev`)",
            "reload: the Reload button or Ctrl+Shift+R in QGIS; quit QGIS to stop",
        ),
        (
            # decision-48 point 5: the two lines a console needs, printed
            # where a developer is already looking.
            f"console: in Plugins > Python Console: import qgis.utils; "
            f'session = qgis.utils.plugins["{facts.project.plugin}"].console() '
            f"(or: from qgis_sdk.console import connect; session = connect())"
        ),
    )


def _validate_desktop_binary(install: QgisInstall) -> None:
    if install.executable is None:
        raise QgisSdkDevError(
            f"{install.prefix} has no QGIS Desktop binary (bin/qgis or "
            "bin/qgis-bin.exe); install QGIS Desktop there, point --qgis-prefix at "
            "one, or use --mode standalone"
        )


def _desktop_argv(install: QgisInstall, state: Path, probe: Path) -> tuple[str, ...]:
    # QGIS appends ``profiles/<name>`` to --profiles-path itself.
    return (
        str(install.executable),
        "--profiles-path",
        str(state),
        "--profile",
        PROFILE_NAME,
        "--code",
        str(probe),
    )


def _desktop_plan(facts: DevFacts) -> DevPlan:
    """The QGIS Desktop binary with an isolated profile and generated host."""
    install = facts.install
    _validate_desktop_binary(install)
    probe = facts.workspace / DESKTOP_PROBE_NAME
    probe.write_text(DESKTOP_PROBE, encoding="utf-8", newline="\n")
    # QGIS appends ``profiles/<name>`` to --profiles-path itself.
    state = facts.project.root / STATE_DIRECTORY
    profile = state / "profiles" / PROFILE_NAME
    process_env = probe_env(facts, headless=facts.headless, desktop=True)
    process_env["QGIS_PLUGINPATH"] = _prepend_path(
        str(facts.host_root), facts.env.get("QGIS_PLUGINPATH")
    )
    return DevPlan(
        mode=facts.mode,
        argv=_desktop_argv(install, state, probe),
        cwd=facts.project.root,
        env=process_env,
        notes=_desktop_notes(facts, install, profile),
        profile=profile,
    )


_DEV_PLANNERS: Final[dict[str, Callable[[DevFacts], DevPlan]]] = {
    "server": server_plan,
    "standalone": _standalone_plan,
    "desktop": _desktop_plan,
}


def plan_dev(
    project: DevProject,
    mode: str,
    install: QgisInstall,
    **options: Unpack[DevOptions],
) -> DevPlan:
    """The QGIS process for ``mode``; the probe it runs is written to ``workspace``.

    ``dev_server`` is the Vite origin to hand the plugin, if one is running.
    ``watch`` makes the Desktop bootstrap reload on saved Python and
    metadata changes (debounced, serialised; see ``devtools.reloader``);
    the Reload button works either way. ``exercise`` makes the bootstrap
    drive itself through the reload policy, write a JSON report there and
    quit. The SDK's own packages join ``PYTHONPATH`` so the bootstrap
    imports inside QGIS's interpreter whichever Python runs the CLI.
    """
    facts = dev_facts(project, mode, install, options)
    return _DEV_PLANNERS[facts.mode](facts)


def _app_flags(options: AppOptions) -> list[str]:
    """The flags ``qgis_sdk.app`` reads, in the order the CLI declares them."""
    flags: list[str] = []
    if not options.get("gui", True):
        flags.append("--headless")
    if options.get("once", False):
        flags.append("--once")
    grace = options.get("grace")
    if grace is not None:
        flags.extend(("--grace", f"{grace:g}"))
    title = options.get("title")
    if title is not None:
        flags.extend(("--title", title))
    return flags


def _app_entry(
    project: DevProject, install: QgisInstall, workspace: Path, flags: Sequence[str]
) -> tuple[tuple[str, ...], str]:
    """Use the project's ``__main__.py``, else write a probe that imports its spec."""
    root = project.root
    entry = root / project.plugin / "__main__.py"
    if entry.is_file():
        return (str(install.python), "-m", project.plugin, *flags), (
            f"{project.plugin} from {entry}"
        )
    probe = workspace / APP_PROBE_NAME
    probe.write_text(_app_probe(project), encoding="utf-8", newline="\n")
    return (str(install.python), str(probe), *flags), (
        f"a generated probe for {project.config.spec} "
        f"(the project has no {project.plugin}/__main__.py)"
    )


def _app_interpreter(install: QgisInstall) -> None:
    """The app host imports PyQGIS into the interpreter it was built for."""
    if install.python is None:
        raise QgisSdkDevError(
            f"{install.prefix} has no Python interpreter, so it cannot run a "
            "standalone app; the app host imports PyQGIS into the interpreter it "
            "was built for"
        )


def _app_plan(
    project: DevProject, install: QgisInstall, options: AppOptions
) -> DevPlan:
    """Assemble the app run: flags, entry, environment and its console note."""
    workspace = Path(options.get("workspace", "."))
    env = options.get("env", {})
    gui = options.get("gui", True)
    argv, where = _app_entry(project, install, workspace, _app_flags(options))
    toolkit_args = options.get("toolkit_args", ())
    if toolkit_args:
        argv = (*argv, "--", *toolkit_args)
    process_env = install.environment(
        env,
        extra_paths=(project.root, *sdk_import_paths()),
        headless=not gui or wants_headless(env),
    )
    note = (
        f"app: {install.python} ({install.source}) running {where}, "
        f"{'with a window' if gui else 'headless'}"
    )
    return plan_app_phase1(argv, gui, note, process_env, project.root)


def plan_app(
    project: DevProject,
    install: QgisInstall,
    **options: Unpack[AppOptions],
) -> DevPlan:
    """The QGIS process that starts ``project`` as a standalone app.

    The entry is the project's own ``<plugin>/__main__.py`` when it has one
    (what ``build --target app`` installs as a launcher); without one a
    generated probe imports ``config.spec`` and calls ``qgis_sdk.app.main``.
    ``gui`` opens the window; ``once`` makes the CI smoke run; ``toolkit_args``
    go after ``--`` so Qt, not the SDK, sees them.
    """
    _require_application(project)
    _app_interpreter(install)
    return _app_plan(project, install, options)


def _require_application(project: DevProject) -> None:
    """Refuse a project whose only host is the server: it declares no application.

    A server plugin's declarations are hooks QGIS Server calls; there is no
    action, no surface and no page for an app host to show, so starting one would
    present an empty window (decision-52 point 1).
    """
    hosts = project.config.hosts
    if {"desktop", "app"} & set(hosts):
        return
    raise QgisSdkDevError(
        f"{project.plugin} declares hosts = [{', '.join(repr(h) for h in hosts)}], "
        "so it is not an application: a server plugin's hooks are called by QGIS "
        "Server, not by an app. Declare `desktop` or `app` in "
        "`[tool.qgis-sdk] hosts` and keep the hooks in a module the server loads "
        "(decision-52 point 1)"
    )


def _app_probe(project: DevProject) -> str:
    """The probe that starts a project without an app entry of its own."""
    module, _, attribute = project.config.spec.partition(":")
    return APP_PROBE.format(module=module, attribute=attribute)


APP_PROBE: Final = '''"""Starts one project as a standalone app; written by `qgis-sdk run`."""

from __future__ import annotations

import importlib

from qgis_sdk.app import main


def _application():
    return getattr(importlib.import_module({module!r}), {attribute!r})


if __name__ == "__main__":
    raise SystemExit(main(_application()))
'''


def _prepend_path(entry: str, existing: str | None) -> str:
    return entry if not existing else os.pathsep.join((entry, existing))


def wait_for_port(port: int, **options: Unpack[WaitOptions1]) -> bool:
    """Wait until ``port`` answers; False when the server died or time ran out."""
    values = WaitValues1(**options)
    deadline = values.clock() + values.timeout
    while values.clock() < deadline:
        if values.probe(port):
            return True
        if not values.still_running():
            return False
        values.sleep(0.1)
    return False


DESKTOP_PROBE: Final = '''"""Load the source plugin and keep it reloadable (qgis-sdk dev)."""

import json
import os
import sys
import traceback
from pathlib import Path

request = json.loads(Path(os.environ["QGIS_SDK_DEV_REQUEST"]).read_text(encoding="utf-8"))

try:
    from qgis_sdk_tools.devtools.bootstrap import bootstrap, report_bootstrap_failure
except BaseException:  # noqa: BLE001 - keep QGIS up, show what happened
    log = sys.__stderr__ or sys.stderr
    log.write("qgis-sdk dev: cannot import qgis_sdk_tools inside QGIS:\\n" + traceback.format_exc())
    log.flush()
    if request.get("exercise"):
        Path(request["exercise"]).write_text(
            json.dumps({"started": False, "error": traceback.format_exc()}), encoding="utf-8"
        )
        os._exit(1)
else:
    try:
        _session = bootstrap(request)  # kept alive: it owns the timers and actions
    except BaseException:  # noqa: BLE001
        report_bootstrap_failure(request.get("exercise"))
'''

__all__ = [
    "free_port",
]
