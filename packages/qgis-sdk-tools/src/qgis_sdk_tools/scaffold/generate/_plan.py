from __future__ import annotations

import re
from pathlib import Path

from qgis_sdk_tools.check.versions import installed_runtime_version
from qgis_sdk_tools.scaffold.options import ScaffoldOptions
from qgis_sdk_tools.scaffold.web import plan_web

from ._facts import (
    ALGORITHM_ACTION,
    ALGORITHM_IMPORTS,
    ALGORITHM_MODELS,
    ALGORITHM_PROVIDERS,
    ALGORITHMS_MODULE,
    ENTRY_POINT,
    LF,
    PLUGIN_MODULE,
    UI_ACTION,
    UI_IMPORTS,
    UI_SURFACES,
    plan_scaffold_facts11,
    starter_test_facts1,
)
from ._templates import (
    APP_MAIN_MODULE,
    APP_STARTER_TEST,
    GITIGNORE,
    PYPROJECT,
    SERVER_ENTRY_POINT,
    SERVER_PLUGIN_MODULE,
    SERVER_STARTER_TEST,
    WEB_TABLE,
    GeneratedFile,
)


def plan_scaffold(options: ScaffoldOptions) -> tuple[GeneratedFile, ...]:
    """Return every file the project needs, ordered so plans compare directly.

    Paths are built from the validated package name, so no entry can escape
    ``target``: an identifier cannot contain a separator or a parent reference.
    """
    from ._readmes import readme

    values = [
        GeneratedFile(".gitignore", GITIGNORE),
        GeneratedFile("README.md", readme(options)),
        GeneratedFile("pyproject.toml", _pyproject(options)),
        GeneratedFile(f"{options.plugin}/__init__.py", _entry_point(options)),
        GeneratedFile(f"{options.plugin}/plugin.py", _plugin_module(options)),
        *(
            (
                GeneratedFile(
                    f"{options.plugin}/__main__.py",
                    APP_MAIN_MODULE.format(title=options.title, plugin=options.plugin),
                ),
            )
            if options.host == "app"
            else ()
        ),
        GeneratedFile("tests/test_plugin.py", _starter_test(options)),
        *(GeneratedFile(path, content) for path, content in plan_web(options)),
    ]
    return plan_scaffold_facts11(options, values)


def write_scaffold(
    options: ScaffoldOptions,
    target: Path,
    *,
    force: bool = False,
) -> tuple[Path, ...]:
    """Create the planned files under ``target`` and return their paths."""
    from ._readmes import refuse_existing

    plan = plan_scaffold(options)
    paths = tuple(target / file.path for file in plan)
    if not force:
        refuse_existing(target, paths)
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
        class_name=class_name(options.plugin),
        host=options.host,
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


def _entry_point(options: ScaffoldOptions) -> str:
    """``<plugin>/__init__.py``: empty except for a server plugin's factory.

    A Desktop plugin's ``classFactory`` is bound by ``build``/``dev``
    (decision-43), so the file stays empty. A server plugin's entry cannot be:
    QGIS Server imports ``serverClassFactory`` from the package itself, and the
    plugin is deployed as the package QGIS already has on its path. An app
    plugin's entry is ``main()`` in ``<plugin>/__main__.py`` - there is no QGIS
    to call a factory, so the package stays import-only.
    """
    if options.host == "server":
        return SERVER_ENTRY_POINT.format(title=options.title)
    return ENTRY_POINT


def _service_name(plugin: str) -> str:
    """The OGC ``SERVICE`` a generated server plugin owns, from its id."""
    return plugin.replace("_", "").upper()


def _plugin_module(options: ScaffoldOptions) -> str:
    if options.host == "server":
        return SERVER_PLUGIN_MODULE.format(
            title=options.title,
            plugin=options.plugin,
            service_name=_service_name(options.plugin),
        )
    return PLUGIN_MODULE.format(
        title=options.title,
        plugin=options.plugin,
        class_name=class_name(options.plugin),
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


def algorithms_module(options: ScaffoldOptions) -> str:
    return ALGORITHMS_MODULE.format(title=options.title, plugin=options.plugin)


def _starter_test(options: ScaffoldOptions) -> str:
    action_ids = sorted(
        ["ping", "project_layers"]
        + (["buffer"] if options.algorithm else [])
        + (["open_ping"] if options.ui else [])
    )
    if options.host == "app":
        return APP_STARTER_TEST.format(
            title=options.title,
            plugin=options.plugin,
            action_ids=", ".join(f'"{identifier}"' for identifier in action_ids),
        )
    if options.host == "server":
        return SERVER_STARTER_TEST.format(
            title=options.title,
            plugin=options.plugin,
            service_name=_service_name(options.plugin),
        )
    return starter_test_facts1(action_ids, options)


def class_name(plugin: str) -> str:
    return "".join(word.capitalize() for word in plugin.split("_"))


def readme_part1(options, plugin) -> str:
    """Part 1 of the generated readme documentation."""
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
"""


def readme_part2(options, plugin) -> str:
    """Part 2 of the generated readme documentation."""
    return f"""`QGIS_PREFIX_PATH`, `qgis` on PATH, or the current environment), starts QGIS
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

"""


def readme_part3(options, plugin) -> str:
    """Part 3 of the generated readme documentation."""
    return f"""Use this when the code runs without QGIS, for example in a plain Qt application
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
"""


def readme_part4(options, plugin) -> str:
    """Part 4 of the generated readme documentation."""
    from ._readmes import algorithm_readme, ui_readme, web_readme

    return f"""
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
{algorithm_readme(options)}{ui_readme(options)}{web_readme(options)}"""


def ui_readme_part1(plugin) -> str:
    """Part 1 of the generated ui_readme documentation."""
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
"""


def ui_readme_part2(plugin) -> str:
    """Part 2 of the generated ui_readme documentation."""
    return f"""same way. Inside the dialog `self.ctx` is a `UiContext`:
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


def web_readme_part1(options, plugin, framework, run, install) -> str:
    """Part 1 of the generated web_readme documentation."""
    return f"""
## Web UI

`web/` is a Vite app ({framework}) that QGIS shows as a {options.web.placement}: the
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

"""
