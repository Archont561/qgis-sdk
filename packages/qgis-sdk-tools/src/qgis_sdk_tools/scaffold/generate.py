"""The file plan for one plugin project, and the only writer that touches disk."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk_tools.check.versions import installed_runtime_version

from .options import QgisSdkScaffoldError, ScaffoldOptions
from .web import install_command, plan_web, script_command

LF: Final = "\n"

#: ``<plugin>/__init__.py`` is empty on purpose (decision-43): QGIS's entry,
#: ``classFactory``, is bound by ``qgis-sdk build`` and ``qgis-sdk dev``.
ENTRY_POINT = ""

PLUGIN_MODULE = '''"""{title}: a minimal qgis-sdk plugin."""

from __future__ import annotations

from qgis_sdk import QgisSdkPlugin{ui_names}
{algorithm_imports}from qgis_sdk.core import PluginContext
{algorithm_models}{ui_imports}

app = QgisSdkPlugin(id="{plugin}", title="{title}")
{algorithm_providers}{ui_surfaces}

@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> int:
    """Return the value unchanged so a caller can prove the round trip."""
    return value


@app.action(id="project_layers", title="Project layers")
def project_layers(ctx: PluginContext) -> list[str]:
    """The same project service a web view reaches as ``host.project``."""
    return list(ctx.project.layer_ids())
{algorithm_action}{ui_action}'''

UI_IMPORTS = """
from .ui import PingDialog
"""

UI_SURFACES = """
app.add_surface(PingDialog)
"""

UI_ACTION = '''

@toolbar(text="{title}")
@app.action(id="open_ping", title="Open ping")
def open_ping(ctx: PluginContext) -> None:
    """A bound, no-input action: the toolbar button opens the dialog."""
    ctx.ui.open(PingDialog, initial={{"value": 7}})
'''

UI_MODULE = '''"""{title}: native surfaces, plain classes built in pure PyQt (decision-55).

The dialog declares its components as class attributes: each takes the
attribute's name, the default ``build()`` stacks them, ``@on(component)``
wires the method, and every opening gets its own copies seeded from
``initial``. The host constructs a ``Dialog`` per opening, binds ``self.ctx``
(a ``UiContext``: ``actions``, ``view``, ``notifications``, ``log``) and
``self.initial``, shows what ``build()`` returns and disposes the scope -
connections included - when the window closes. Nothing here imports Qt, so
the module stays importable by the pure tests, ``describe_bindings`` and
``qgis-sdk check``; a ``build()`` returning any QWidget is the escape hatch.
"""

from __future__ import annotations

from qgis_sdk import menu
from qgis_sdk.ui import Button, Dialog, Form, LogView, Number, on


@menu("Plugins/{title}")
class PingDialog(Dialog):
    """Ask for a number and show what the ``ping`` action answers."""

    title = "{title}: ping"

    value = Number(integer=True, required=True)  # objectName form/value
    form = Form([value], action_id="ping")  # submits through ctx.actions
    ping = Button(text="Ping")  # objectName buttons/ping
    answers = LogView(label="Answers")  # shows ctx.log as it arrives

    @on(ping).clicked  # connected after build(); gone with the window
    def pinged(self) -> None:
        """Call the plugin's own action through the validated, view-scoped path."""
        answer = self.form.submit()
        self.ctx.log.info("pong", value=answer)
'''

ALGORITHM_IMPORTS = """from qgis_sdk.algorithms import invoke
"""

ALGORITHM_MODELS = """from qgis_sdk.models import CrsInput, LayerInput, Metres, VectorLayerInfo

from . import algorithms
"""

ALGORITHM_PROVIDERS = """
app.add_provider(algorithms.provider)
"""

ALGORITHM_ACTION = '''

@app.action(id="buffer", title="Buffer a layer")
def buffer(
    ctx: PluginContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Run the same algorithm the toolbox offers, from a native or web surface."""
    return invoke(
        algorithms.buffer_layer, ctx, layer_id=layer_id,
        distance_metres=distance_metres, working_crs=working_crs,
    )
'''

ALGORITHMS_MODULE = '''"""The Processing algorithms {title} owns (decision-42).

One provider, one function. The function binds typed inputs to the produced
layer through the injected ``ctx.algorithms``; request validation and the
Processing call belong to the SDK, so the same function runs against the
in-memory fake in a QGIS-free test and against Processing inside QGIS.
"""

from __future__ import annotations

from qgis_sdk.core import AlgorithmContext
from qgis_sdk.models import BufferRequest, CrsInput, LayerInput, Metres, VectorLayerInfo
from qgis_sdk.providers import Provider

provider = Provider(id="{plugin}", title="{title}")


@provider.algorithm(id="buffer", title="Buffer a layer in an explicit working CRS")
def buffer_layer(
    ctx: AlgorithmContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Buffer ``layer_id`` by ``distance_metres`` inside the projected ``working_crs``."""
    return ctx.algorithms.execute(
        BufferRequest(
            layer_id=layer_id,
            distance_metres=distance_metres,
            working_crs=working_crs,
        )
    )
'''

STARTER_TEST = '''"""Smoke tests for {title}. They need no QGIS install and no display.

``host()`` is what `qgis-sdk build` and `qgis-sdk dev` bind as ``classFactory``;
outside QGIS it gives the plugin a bare context, so these tests run the real
lifecycle against the SDK's own refusals.
"""

import pytest
from qgis_sdk import describe
from qgis_sdk.adapters.desktop import host

from {plugin}.plugin import app

classFactory = host("{plugin}.plugin:app"{host_arguments})


def test_the_plugin_starts_and_unloads_without_a_host() -> None:
    plugin = classFactory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.state.value == "running"
        assert plugin.runtime.actions["ping"](7) == 7
    finally:
        plugin.unload()
    assert plugin.runtime.state.value == "stopped"


def test_declared_actions_are_the_plugins_public_surface() -> None:
    description = describe(app)

    assert [action.id for action in description.actions] == [{action_ids}]


def test_a_service_the_host_did_not_supply_is_refused_by_name() -> None:
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    plugin = classFactory(None)
    plugin.initGui()
    try:
        with pytest.raises(QgisSdkUnsupportedCapabilityError):
            plugin.runtime.actions["project_layers"]()
    finally:
        plugin.unload()
{algorithm_test}{ui_test}'''

UI_TEST = """

def test_the_bound_action_opens_the_dialog_under_the_fake_ui() -> None:
    from qgis_sdk.core import PluginContext, ResourceScope
    from qgis_sdk.testing import FakeUi, RecordingNotifications
    from {plugin}.plugin import open_ping
    from {plugin}.ui import PingDialog

    scope = ResourceScope()
    ui = FakeUi(scope)
    context = PluginContext(notifications=RecordingNotifications(scope), scope=scope, ui=ui)
    open_ping(context)
    assert [opened.surface for opened in ui.opened] == [PingDialog]
    assert dict(ui.opened[0].initial) == {{"value": 7}}
    scope.close()
"""

ALGORITHM_TEST = '''

def test_the_buffer_algorithm_asks_processing_for_exactly_the_request(tmp_path) -> None:
    """The SDK fakes stand in for Processing: what was asked, and what came back."""
    from qgis_sdk.algorithms import invoke
    from qgis_sdk.core import PluginContext, ResourceScope
    from qgis_sdk.models import BufferRequest
    from qgis_sdk.testing import (
        FakeAlgorithms,
        FakeLayers,
        FakeProject,
        RecordingNotifications,
    )

    from {plugin}.algorithms import buffer_layer, provider

    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        tmp_path / "points.gpkg", name="points", geometry_type="point", field_names=("id",)
    )
    algorithms = FakeAlgorithms(layers, scope)
    algorithms.declare_output(
        BufferRequest,
        tmp_path / "buffer.gpkg",
        name="buffer",
        geometry_type="polygon",
        field_names=("id",),
        crs="EPSG:3857",
    )
    project = FakeProject(layers, scope)
    ctx = PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        layers=layers,
        project=project,
        algorithms=algorithms,
    )
    source = layers.open_vector(tmp_path / "points.gpkg")

    output = invoke(
        buffer_layer, ctx, layer_id=source.id, distance_metres=25.0, working_crs="EPSG:3857"
    )

    assert provider.algorithms == (buffer_layer,)
    assert output.name == "buffer" and output.geometry_type == "polygon"
    (request,) = algorithms.requests
    assert request == BufferRequest(
        layer_id=source.id, distance_metres=25.0, working_crs="EPSG:3857"
    )
    assert project.layer_ids() == (output.id,)
    scope.close()
'''

PYPROJECT = """# Generated by `qgis-sdk new`. The project is the plugin: `qgis-sdk dev` runs
# this directory inside QGIS and `qgis-sdk build` turns it into the ZIP. QGIS's
# metadata.txt and classFactory are derived from this file (decision-43).
[project]
name = "{name}"
version = "{version}"
description = "{description}"
authors = [{{ name = "{author}", email = "{email}" }}]
requires-python = ">=3.11"
# The runtime the plugin is written for; `build` vendors the installed one and
# `check` reports a mismatch (VERSION004). `qgis-sdk` itself never installs.
dependencies = ["{runtime_requirement}"]

[dependency-groups]
dev = ["{tools_requirement}"]

[tool.qgis-sdk]
# The application QGIS runs; `build` and `dev` bind classFactory to it through
# qgis_sdk.adapters.desktop.host().
plugin = "{plugin}.plugin:app"
qgis-minimum-version = "{qgis_minimum_version}"
experimental = true
# Where QGIS is, when `qgis-sdk test` and `qgis-sdk dev` should not discover it
# (they otherwise try QGIS_PREFIX_PATH, `qgis` on PATH, then this environment).
# qgis-prefix = "/path/to/qgis"

# Extra metadata.txt keys, passed through as written:
# [tool.qgis-sdk.metadata]
# homepage = "https://example.org/{name}"
# tags = "vector"
{web_table}
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
# The SDK's pytest plugin: the `qgis` and `desktop` markers, the `qgis_app` and
# `qgis_iface` fixtures, and the guard `qgis-sdk test` relies on. Plain `pytest`
# keeps working; `qgis-sdk test --target qgis|desktop` runs the native layers.
addopts = "-p qgis_sdk_tools.pytest_plugin"
"""

WEB_TABLE = """
[tool.qgis-sdk.web]
# The page in web/: shown as a {placement}; `grants` lists the host grants
# (`layers.read`) or operation ids (`project.layer_ids`) the page may use;
# `qgis-sdk bridge generate --host` renders the catalogue. The starter page's
# layer picker reads `layers.list`, which `layers.read` covers, and
# `algorithms.run` lets `runAlgorithm` from web/src/processing.schema.ts run
# the host's Processing algorithms.
placement = "{placement}"
grants = ["layers.read", "algorithms.run"]
"""

GITIGNORE = """__pycache__/
.pytest_cache/
# `qgis-sdk dev` keeps its isolated QGIS profile and the generated host package here.
.qgis-sdk/
# `qgis-sdk build` writes the installable ZIP here.
dist/
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
        GeneratedFile("pyproject.toml", _pyproject(options)),
        GeneratedFile(f"{options.plugin}/__init__.py", ENTRY_POINT),
        GeneratedFile(f"{options.plugin}/plugin.py", _plugin_module(options)),
        GeneratedFile("tests/test_plugin.py", _starter_test(options)),
        *(GeneratedFile(path, content) for path, content in plan_web(options)),
    ]
    if options.algorithm:
        values.append(
            GeneratedFile(
                f"{options.plugin}/algorithms.py", _algorithms_module(options)
            )
        )
    if options.ui == "native":
        values.append(
            GeneratedFile(
                f"{options.plugin}/ui.py", UI_MODULE.format(title=options.title)
            )
        )
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


def _pyproject(options: ScaffoldOptions) -> str:
    runtime, tools = sdk_requirements()
    web_table = (
        "" if options.web is None else WEB_TABLE.format(placement=options.web.placement)
    )
    return PYPROJECT.format(
        name=options.plugin.replace("_", "-"),
        version=options.version,
        description=f"{options.title}: a minimal qgis-sdk plugin.",
        author=options.author,
        email=options.email,
        runtime_requirement=runtime,
        tools_requirement=tools,
        plugin=options.plugin,
        class_name=_class_name(options.plugin),
        qgis_minimum_version=options.qgis_minimum_version,
        web_table=web_table,
    )


def sdk_requirements() -> tuple[str, str]:
    """``qgis-sdk-runtime>=X.Y,<X.Y+1`` and the same for the tools, from this install.

    ``X.Y`` is the installed runtime's minor (the checkout's manifest when
    the tools run from source); the tools follow at the same number, which
    is how the kit releases them.
    """
    version = installed_runtime_version() or "0.0"
    digits = re.match(r"(\d+)(?:\.(\d+))?", version)
    major, minor = (
        (int(digits.group(1)), int(digits.group(2) or 0)) if digits else (0, 0)
    )
    window = f">={major}.{minor},<{major}.{minor + 1}"
    return f"qgis-sdk-runtime{window}", f"qgis-sdk-tools{window}"


def _plugin_module(options: ScaffoldOptions) -> str:
    return PLUGIN_MODULE.format(
        title=options.title,
        plugin=options.plugin,
        class_name=_class_name(options.plugin),
        algorithm_imports=ALGORITHM_IMPORTS if options.algorithm else "",
        algorithm_models=ALGORITHM_MODELS if options.algorithm else "",
        algorithm_providers=(
            ALGORITHM_PROVIDERS.format(plugin=options.plugin)
            if options.algorithm
            else ""
        ),
        algorithm_action=ALGORITHM_ACTION if options.algorithm else "",
        ui_names=", toolbar" if options.ui else "",
        ui_imports=UI_IMPORTS if options.ui else "",
        ui_surfaces=UI_SURFACES if options.ui else "",
        ui_action=UI_ACTION.format(title=options.title) if options.ui else "",
    )


def _algorithms_module(options: ScaffoldOptions) -> str:
    return ALGORITHMS_MODULE.format(title=options.title, plugin=options.plugin)


def _starter_test(options: ScaffoldOptions) -> str:
    action_ids = sorted(
        ["ping", "project_layers"]
        + (["buffer"] if options.algorithm else [])
        + (["open_ping"] if options.ui else [])
    )
    return STARTER_TEST.format(
        title=options.title,
        plugin=options.plugin,
        action_ids=", ".join(f'"{identifier}"' for identifier in action_ids),
        algorithm_test=(
            ALGORITHM_TEST.format(plugin=options.plugin) if options.algorithm else ""
        ),
        ui_test=(
            UI_TEST.format(
                plugin=options.plugin, class_name=_class_name(options.plugin)
            )
            if options.ui
            else ""
        ),
        class_name=_class_name(options.plugin),
        host_arguments=(
            "" if options.web is None else f', placement="{options.web.placement}"'
        ),
    )


def _class_name(plugin: str) -> str:
    return "".join(word.capitalize() for word in plugin.split("_"))


def _readme(options: ScaffoldOptions) -> str:
    plugin = options.plugin
    return f"""# {options.title}

A minimal [qgis-sdk](https://pypi.org/project/qgis-sdk/) plugin generated by
`qgis-sdk new`. `{plugin}/plugin.py` holds the application and its actions,
without Qt or QGIS imports, `classFactory`, or `metadata.txt`.
`pyproject.toml` names the application
(`[tool.qgis-sdk] plugin`) and the few facts QGIS needs; `qgis-sdk build` and
`qgis-sdk dev` derive the QGIS entry from them. Replace the generated author
and email in `[project]` before publishing anywhere.

## Desktop mode

Use this when the plugin runs inside QGIS, which is the only host that provides
`iface`:

```sh
qgis-sdk dev
```

finds QGIS (`--qgis-prefix`, `[tool.qgis-sdk] qgis-prefix` in pyproject.toml,
`QGIS_PREFIX_PATH`, `qgis` on PATH, or the current environment), starts QGIS
Desktop with its own profile in `.qgis-sdk/profiles/dev`, writes a small host
package to `.qgis-sdk/dev/host/{plugin}/` (`metadata.txt` plus a
`classFactory` bound through `qgis_sdk.adapters.desktop.host()`) and puts that
directory on `QGIS_PLUGINPATH`, so QGIS loads `{plugin}/` from source, in
place. Saving a Python file (or the Reload button, Ctrl+Shift+R) unloads and
starts the current source again; a `pyproject.toml` change needs a new
`qgis-sdk dev`. A syntax error refuses the reload and keeps the running
revision; work that cannot stop within two seconds refuses it too and is named;
if unloading or starting fails the plugin stays disabled and the message says
so - restart `qgis-sdk dev`. `--no-watch` leaves reloads to the button. Quit
QGIS to stop.

To install into a real profile instead, `qgis-sdk build` writes
`dist/{plugin}-<version>.zip` with `metadata.txt`, the `classFactory` line and
the SDK runtime inside, and Plugins > Manage and Install Plugins > Install from
ZIP installs it in any supported QGIS without qgis-sdk.

## Standalone Qt mode

Use this when the code runs without QGIS, for example in a plain Qt application
or in the starter tests. `host()` gives the plugin exactly what the process can
offer:

```python
from qgis_sdk.adapters.desktop import host

plugin = host("{plugin}.plugin:app")(None)
plugin.initGui()
```

Without a `QgsApplication` the context has no `desktop`, so reading
`ctx.desktop` raises `QgisSdkUnsupportedCapabilityError` with
`code="unsupported_capability"` instead of inventing a host: standalone mode
provides no `iface`, no message bar and no plugin lifecycle. Informational
messages are dropped, because the notifications service has no bar to write
to. `qgis-sdk dev --mode standalone` runs the same entry in a bare
`QgsApplication`: no Desktop, no reload, close the window to stop. Run Qt
without a display by setting `QT_QPA_PLATFORM=offscreen`, which is what the
workspace smokes do.

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
{_algorithm_readme(options)}{_ui_readme(options)}{_web_readme(options)}"""


def _ui_readme(options: ScaffoldOptions) -> str:
    if options.ui != "native":
        return ""
    plugin = options.plugin
    return f"""
## Native UI

`{plugin}/ui.py` holds `PingDialog`, a `Dialog` subclass that declares its
components as class attributes: a `Number` named after its attribute
(`form/value`), a `Form` over the `ping` action, a `Button` and a `LogView`
over `ctx.log`. The default `build()` stacks them, `initial` seeds the
inputs by name, and every opening gets its own copies, so no Qt is imported
anywhere in the package. A `build()` returning any QWidget is the escape
hatch when the catalogue lacks a widget (plain PyQt, imported inside the
method; `Form.for_action(self.ctx, "ping")` builds the inputs from the
action's declaration there too); see the `simple` example's `surfaces.py`
for both forms and its `ResultsDock` for a `Dock` of containers, a
`ResultTable` and a `LogView`. `@menu("Plugins/...")` on the class puts it
in the Plugins menu, `plugin.py` lists it in `surfaces` and binds the
no-input `open_ping` action to the toolbar, which calls
`self.ctx.ui.open(PingDialog, initial=...)`. The method under
`@on(ping).clicked` is connected to that window's copy of the button after
`build()` and disconnected with the window; `@on("name")` targets an
`objectName` instead, and `ui = "ping.ui"` loads a Qt Designer file the
same way. Inside the dialog `self.ctx` is a `UiContext`:
`self.form.submit()` dispatches the plugin's own action with validation,
`self.ctx.view.request_close()` closes the window. `qgis-sdk check` reads
the surfaces: every interactive widget a `build()` constructs needs
`setObjectName` (`UI001`; the catalogue's components name theirs), an `@on`
name must exist in the `.ui` file (`UI002`), a bound action with inputs
needs a surface that collects them (`UI003`), Qt imported at module level
in the package is warned about (`UI004`), `@on(attribute)` must name a
component and a declared `Custom` must take a factory, not a widget
(`UI005`), and `@toolbar(icon="name.svg")` names a file under
`{plugin}/icons/` (`ICON001`). The starter test drives the action under
`qgis_sdk.testing.FakeUi` without QGIS.
"""


def _algorithm_readme(options: ScaffoldOptions) -> str:
    if not options.algorithm:
        return ""
    plugin = options.plugin
    return f"""
## Processing

`{plugin}/algorithms.py` holds the Processing provider the plugin owns and one
function algorithm, `buffer_layer`; `plugin.py` lists the provider
(`providers = (algorithms.provider,)`) and exposes the same operation as the
`buffer` action. While the plugin is loaded the toolbox shows it as
`{plugin}:buffer`, with parameters derived from the function's typed inputs;
`metadata.txt` gets `hasProcessingProvider=yes` from the same declaration.
Add an algorithm by adding a decorated function; the starter test in
`tests/test_plugin.py` shows how the SDK fakes stand in for Processing.
"""


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
`QgisSdk` built on `web/src/bridge.schema.ts`, generated from the declarations
in `{plugin}/plugin.py` and checked in. Next to it, `web/src/processing.schema.ts`
types the host's own Processing algorithms (`native`, from the SDK's snapshot
to start): `runAlgorithm(qgis, "native:buffer", {{ INPUT }})` from it runs any
of them behind the `algorithms.run` grant. Run `{run.format(script="bindings")}`
in CI (it runs `qgis-sdk bridge generate --check` and `qgis-sdk processing
generate --check` against your QGIS) so neither file can drift.

```sh
cd web
{install}
{run.format(script="test")}     # Vitest against the scripted host in @archont561/qgis-sdk/testing
{run.format(script="build")}    # writes {plugin}/web/index.html and its assets
```

`qgis-sdk dev` starts the Vite dev server on loopback and the page is served
from it inside QGIS, with hot module replacement (`qgis-sdk test --target web`
runs the Vitest suite). Without the command, build before enabling the plugin:
the SDK's page view loads `{plugin}/web/index.html` from disk and shows a hint
until it exists. The page is confined to that directory and reaches no remote
origin; `[tool.qgis-sdk.web]` in pyproject.toml chooses the placement and
lists the curated host operations (`grants`) the page may call - `layers.read`
for the layer picker and `algorithms.run` for the typed Processing runner, to
start. A build never references the dev server.
Dependencies are pinned to the versions this SDK release was qualified with;
the Chromium target in `web/vite.config.ts` follows the oldest QGIS you
support.

The starter page is two stores from the SDK, no framework glue of its own: a
form over the declared `ping` action (`formStore`, fields from the schema,
values validated before a call) and a layer picker over the host's layer list
(`layersQuery`, which says so when the page was not granted it). The same
stores drive `@archont561/qgis-sdk/react`, `/vue` and `/svelte`.
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
