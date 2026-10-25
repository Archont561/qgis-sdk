"""The file plan for one plugin project, and the only writer that touches disk."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .options import QgisSdkScaffoldError, ScaffoldOptions
from .web import install_command, plan_web, script_command

LF: Final = "\n"

ENTRY_POINT = '''"""QGIS imports ``classFactory(iface)`` from this module."""

from .plugin import classFactory

__all__ = ["classFactory"]
'''

PLUGIN_MODULE = '''"""{title}: a minimal qgis-sdk plugin."""

from __future__ import annotations

from qgis_sdk import action, plugin
from qgis_sdk.adapters.desktop import create_class_factory
from qgis_sdk.core import PluginContext, ResourceScope
{web_import}

class MessageBarNotifications:
    """Send informational messages to the host message bar, if there is one."""

    def __init__(self, iface: object | None) -> None:
        self._iface = iface

    def info(self, message: str) -> None:
        # ``QgisInterface.messageBar`` is a method, and the bar exists only when a
        # host supplied an interface, so a plain attribute lookup would crash here.
        if self._iface is None:
            return
        self._iface.messageBar().pushInfo("{title}", message)


@plugin(id="{plugin}", title="{title}")
class {class_name}Plugin:
    """Declared actions only: no Qt imports and no framework glue to memorise."""

    ctx: PluginContext  # bound by the runtime while the plugin is loaded

    @action(id="ping", title="Ping")
    def ping(self, value: int) -> int:
        """Return the value unchanged so a caller can prove the round trip."""
        return value

    @action(id="project_layers", title="Project layers")
    def project_layers(self) -> list[str]:
        """The same project service a web view reaches as ``host.project``."""
        return list(self.ctx.require_project().layer_ids())


def build_context(iface: object | None) -> PluginContext:
    """Give the plugin exactly the capabilities this host can offer.

    Inside a running QGIS every curated service is wired from PyQGIS; in a bare
    interpreter (these tests) the context carries notifications and a scope,
    and ``require_<service>()`` refuses by name instead of failing obscurely.
    """
    scope = ResourceScope()
    notifications = MessageBarNotifications(iface)
    if _qgis_is_running():
        from qgis_sdk.adapters.qgis import native_plugin_context

        return native_plugin_context(
            scope, settings_prefix="{plugin}", iface=iface, notifications=notifications
        )
    return PluginContext(notifications=notifications, scope=scope)


def _qgis_is_running() -> bool:
    try:
        from qgis.core import QgsApplication
    except ImportError:
        return False
    return QgsApplication.instance() is not None


{class_factory}'''

PLAIN_CLASS_FACTORY = """classFactory = create_class_factory({class_name}Plugin, context_factory=build_context)
"""

# With a web UI, QGIS holds a small wrapper: the SDK lifecycle as before plus
# one toolbar button that opens the page. ``webview`` imports Qt inside its
# functions, so this module still loads without QGIS.
WEB_CLASS_FACTORY = """_lifecycle = create_class_factory({class_name}Plugin, context_factory=build_context)


class {class_name}Desktop:
    \"\"\"What QGIS holds: the SDK lifecycle plus one toolbar button for the page.\"\"\"

    def __init__(self, iface: object | None) -> None:
        self._iface = iface
        self._plugin = _lifecycle(iface)
        self._action: object | None = None
        self._view: object | None = None

    @property
    def runtime(self) -> object:
        \"\"\"The SDK runtime: the tests read it, the view's dispatcher is built from it.\"\"\"
        return self._plugin.runtime

    def initGui(self) -> None:
        self._plugin.initGui()
        self._action = webview.add_toolbar_action(self._iface, "{title}", self.show_view)

    def show_view(self) -> None:
        \"\"\"Open the page on first use; bring it to the front after that.\"\"\"
        if self._view is None:
            self._view = webview.open_view(
                self.runtime, self._iface, placement="{placement}"
            )
        self._view.show()
        self._view.raise_()

    def unload(self) -> None:
        if self._view is not None:
            webview.close_view(self._view, self._iface)
            self._view = None
        webview.remove_toolbar_action(self._iface, self._action)
        self._action = None
        self._plugin.unload()


def classFactory(iface: object | None) -> {class_name}Desktop:
    \"\"\"QGIS calls this with its interface; the starter tests call it with ``None``.\"\"\"
    return {class_name}Desktop(iface)
"""

STARTER_TEST = '''"""Smoke tests for {title}. They need no QGIS install and no display."""

import pytest
import {plugin}
from qgis_sdk import describe_plugin


def test_class_factory_starts_and_unloads_without_a_host() -> None:
    plugin = {plugin}.classFactory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.state.value == "running"
        assert plugin.runtime.actions["ping"](7) == 7
    finally:
        plugin.unload()
    assert plugin.runtime.state.value == "stopped"


def test_declared_actions_are_the_plugins_public_surface() -> None:
    description = describe_plugin({plugin}.plugin.{class_name}Plugin)

    assert [action.id for action in description.actions] == ["ping", "project_layers"]


def test_a_service_the_host_did_not_supply_is_refused_by_name() -> None:
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    plugin = {plugin}.classFactory(None)
    plugin.initGui()
    try:
        with pytest.raises(QgisSdkUnsupportedCapabilityError):
            plugin.runtime.actions["project_layers"]()
    finally:
        plugin.unload()
'''

PYPROJECT = """# Generated by `qgis-sdk new`. A plugin project needs no build step: QGIS
# imports the plugin package straight from a profile directory.
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
# The SDK's pytest plugin: the `qgis` and `desktop` markers, the `qgis_app` and
# `qgis_iface` fixtures, and the guard `qgis-sdk test` relies on. Plain `pytest`
# keeps working; `qgis-sdk test --target qgis|desktop` runs the native layers.
addopts = "-p qgis_sdk_tools.pytest_plugin"

[tool.qgis-sdk]
# Where QGIS is, when `qgis-sdk test` and `qgis-sdk dev` should not discover it
# (they otherwise try QGIS_PREFIX_PATH, `qgis` on PATH, then this environment).
# qgis-prefix = "/path/to/qgis"
"""

GITIGNORE = """__pycache__/
.pytest_cache/
# `qgis-sdk dev` keeps its isolated QGIS profile here.
.qgis-sdk/
"""


@dataclass(frozen=True, slots=True)
class GeneratedFile:
    """One file of the plan: a project-relative path and its exact content."""

    path: str
    content: str


def plan_scaffold(options: ScaffoldOptions) -> tuple[GeneratedFile, ...]:
    """Return every file the project needs, ordered so plans compare directly.

    Paths are built from the validated package name, so no entry can escape
    ``target``: an identifier cannot contain a separator or a parent reference.
    """
    values = [
        GeneratedFile(".gitignore", GITIGNORE),
        GeneratedFile("README.md", _readme(options)),
        GeneratedFile("pyproject.toml", PYPROJECT),
        GeneratedFile(f"{options.plugin}/metadata.txt", _metadata(options)),
        GeneratedFile(f"{options.plugin}/__init__.py", ENTRY_POINT),
        GeneratedFile(f"{options.plugin}/plugin.py", _plugin_module(options)),
        GeneratedFile("tests/test_plugin_smoke.py", _starter_test(options)),
        *(GeneratedFile(path, content) for path, content in plan_web(options)),
    ]
    return tuple(sorted(values, key=lambda file: file.path))


def write_scaffold(
    options: ScaffoldOptions,
    target: Path,
    *,
    force: bool = False,
) -> tuple[Path, ...]:
    """Create the planned files under ``target`` and return their paths."""
    plan = plan_scaffold(options)
    paths = tuple(target / file.path for file in plan)
    if not force:
        _refuse_existing(target, paths)
    for path, file in zip(paths, plan, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file.content, encoding="utf-8", newline=LF)
    return paths


def _metadata(options: ScaffoldOptions) -> str:
    fields = (
        ("name", options.title),
        ("description", f"{options.title}: a minimal qgis-sdk plugin."),
        ("about", f"{options.title} was generated by `qgis-sdk new`."),
        ("version", options.version),
        ("qgisMinimumVersion", options.qgis_minimum_version),
        ("author", options.author),
        ("email", options.email),
        ("experimental", "True"),
        ("hasProcessingProvider", "No"),
    )
    lines = ["[general]", *(f"{key}={value}" for key, value in fields)]
    return LF.join(lines) + LF


def _plugin_module(options: ScaffoldOptions) -> str:
    class_name = _class_name(options.plugin)
    if options.web is None:
        web_import = ""
        class_factory = PLAIN_CLASS_FACTORY.format(class_name=class_name)
    else:
        web_import = "from . import webview\n"
        class_factory = WEB_CLASS_FACTORY.format(
            class_name=class_name,
            title=options.title,
            placement=options.web.placement,
        )
    return PLUGIN_MODULE.format(
        title=options.title,
        plugin=options.plugin,
        class_name=class_name,
        web_import=web_import,
        class_factory=class_factory,
    )


def _starter_test(options: ScaffoldOptions) -> str:
    return STARTER_TEST.format(
        title=options.title,
        plugin=options.plugin,
        class_name=_class_name(options.plugin),
    )


def _class_name(plugin: str) -> str:
    return "".join(word.capitalize() for word in plugin.split("_"))


def _readme(options: ScaffoldOptions) -> str:
    plugin = options.plugin
    return f"""# {options.title}

A minimal [qgis-sdk](https://pypi.org/project/qgis-sdk/) plugin generated by
`qgis-sdk new`. {plugin}/plugin.py holds the whole design: one `@plugin`
class, one `@action`, and `classFactory` built by the SDK's Desktop adapter.
Nothing is hidden behind generated boilerplate, and no Qt or QGIS import appears
in the file that declares the plugin.

{plugin}/metadata.txt carries the fields QGIS requires (`name`, `description`,
`version`, `qgisMinimumVersion`). Replace the generated author and email before
publishing anywhere.

## Desktop mode

Use this when the plugin runs inside QGIS, which is the only host that provides
`iface`:

```sh
qgis-sdk dev
```

finds QGIS (`--qgis-prefix`, `[tool.qgis-sdk] qgis-prefix` in pyproject.toml,
`QGIS_PREFIX_PATH`, `qgis` on PATH, or the current environment), starts QGIS
Desktop with its own profile in `.qgis-sdk/profiles/dev`, and puts this
directory on `QGIS_PLUGINPATH` so QGIS loads `{plugin}/` from source. QGIS
imports `{plugin}.classFactory`, calls it with its interface, then calls
`initGui()`; saving a Python or metadata file (or the Reload button,
Ctrl+Shift+R) unloads and starts the current source again. A syntax error
refuses the reload and keeps the running revision; work that cannot stop
within two seconds refuses it too and is named; if unloading or starting fails
the plugin stays disabled and the message says so - restart `qgis-sdk dev`.
`--no-watch` leaves reloads to the button. Quit QGIS to stop.

To install into a real profile instead, copy or symlink `{plugin}/` into
`<profile>/python/plugins/` and enable {options.title!r} in Plugins, then
Manage and Install Plugins.

## Standalone Qt mode

Use this when the code runs without QGIS, for example in a plain Qt application
or in the starter tests. Build the context yourself and pass no interface:

```python
from {plugin}.plugin import build_context

context = build_context(None)
```

`context.desktop` is then `None`, so `context.require_native()` raises
`QgisSdkUnsupportedCapabilityError` with `code="unsupported_capability"` instead
of inventing a host: standalone mode provides no `iface`, no message bar and no
plugin lifecycle. Informational messages are dropped, because the notifications
service has no bar to write to. `qgis-sdk dev --mode standalone` runs exactly
this in a bare `QgsApplication`: no Desktop, no reload, close the window to
stop. Run Qt without a display by setting `QT_QPA_PLATFORM=offscreen`, which is
what the workspace smokes do.

## Tests

```sh
qgis-sdk test                    # pure: no QGIS, native imports refused
qgis-sdk test --target qgis      # tests marked `qgis`, headless QgsApplication (`qgis_app`)
qgis-sdk test --target desktop   # tests marked `desktop`, inside QGIS Desktop (`qgis_iface`)
pytest -q                        # the same suite, your way
```

Arguments the command does not know go to pytest (`qgis-sdk test -x -k ping`).
A native target whose QGIS cannot be found fails; one whose tests all skipped
fails too.
{_web_readme(options)}"""


def _web_readme(options: ScaffoldOptions) -> str:
    web = options.web
    if web is None:
        return ""
    plugin = options.plugin
    manager = web.package_manager
    run = " ".join(script_command(manager, "{script}"))
    install = " ".join(install_command(manager))
    framework = "React" if web.framework == "react" else "vanilla TypeScript"
    return f"""
## Web UI

`web/` is a Vite app ({framework}) that QGIS shows as a {web.placement}: the
{options.title!r} toolbar button opens it. The page talks to the plugin through
the typed client in `web/src/bridge.ts`, generated from the declarations in
`{plugin}/plugin.py` and checked in. Run `{run.format(script="bindings")}` in CI
(it runs `qgis-sdk bridge generate --check`) so the file cannot drift from them.

```sh
cd web
{install}
{run.format(script="test")}     # Vitest against the scripted host in @archont561/qgis-sdk/testing
{run.format(script="build")}    # writes {plugin}/web/index.html and its assets
```

`qgis-sdk dev` starts the Vite dev server on loopback and the page is served
from it inside QGIS, with hot module replacement (`qgis-sdk test --target web`
runs the Vitest suite). Without the command, build before enabling the plugin:
`{plugin}/webview.py` loads `{plugin}/web/index.html` from disk and shows a
hint until it exists. The page is confined to that directory by
`BrowserPolicy(asset_roots=...)` and reaches no remote origin until you grant
one there; a build never references the dev server. Dependencies are pinned to the
versions this SDK release was qualified with; the Chromium target in
`web/vite.config.ts` follows the oldest QGIS you support.
"""


def _refuse_existing(target: Path, paths: Sequence[Path]) -> None:
    clashes = sorted(
        path.relative_to(target).as_posix() for path in paths if path.exists()
    )
    if clashes:
        raise QgisSdkScaffoldError(
            "Refusing to overwrite existing files: "
            + ", ".join(clashes)
            + " (pass --force to regenerate them deliberately)"
        )
