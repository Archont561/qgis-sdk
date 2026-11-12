from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from qgis_sdk_tools.scaffold.options import QgisSdkScaffoldError, ScaffoldOptions
from qgis_sdk_tools.scaffold.web import install_command, script_command

from ._plan import (
    readme_part1,
    readme_part2,
    readme_part3,
    readme_part4,
    ui_readme_part1,
    ui_readme_part2,
    web_readme_part1,
)
from ._templates import SERVER_README


def _web_readme_part2(options, plugin, framework, run, install) -> str:
    """Part 2 of the generated web_readme documentation."""
    return f"""`qgis-sdk dev` starts the Vite dev server on loopback and the page is served
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


def readme(options: ScaffoldOptions) -> str:
    plugin = options.plugin
    if options.host == "server":
        return SERVER_README.format(title=options.title, plugin=options.plugin)
    return (
        readme_part1(options, plugin)
        + readme_part2(options, plugin)
        + readme_part3(options, plugin)
        + readme_part4(options, plugin)
    )


def ui_readme(options: ScaffoldOptions) -> str:
    if options.ui != "native":
        return ""
    plugin = options.plugin
    return ui_readme_part1(plugin) + ui_readme_part2(plugin)


def algorithm_readme(options: ScaffoldOptions) -> str:
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


def web_readme(options: ScaffoldOptions) -> str:
    web = options.web
    if web is None:
        return ""
    plugin = options.plugin
    manager = web.package_manager
    run = " ".join(script_command(manager, "{script}"))
    install = " ".join(install_command(manager))
    framework = "React" if web.framework == "react" else "vanilla TypeScript"
    return web_readme_part1(
        options, plugin, framework, run, install
    ) + _web_readme_part2(options, plugin, framework, run, install)


def refuse_existing(target: Path, paths: Sequence[Path]) -> None:
    clashes = sorted(
        path.relative_to(target).as_posix() for path in paths if path.exists()
    )
    if clashes:
        raise QgisSdkScaffoldError(
            "Refusing to overwrite existing files: "
            + ", ".join(clashes)
            + " (pass --force to regenerate them deliberately)"
        )
