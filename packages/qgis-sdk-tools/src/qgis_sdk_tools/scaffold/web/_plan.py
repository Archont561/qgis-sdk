"""The web half of a generated project: a Vite app and the view that shows it.

Everything here is text with a few validated values in it. The templates are
controlled (decision-18): every npm dependency is pinned to the exact version
this SDK release was qualified with, the Chromium target is the one the
oldest supported QGIS ships, and the page's schema module is rendered from
the plugin's own declarations so the checked-in bindings cannot drift from
them; the page builds its `QgisSdk` on that module (decision-44).
Bunup is the workspace's library tooling and never an application's: a Bun
project gets Vite and Vitest like the others.
"""

from __future__ import annotations

import json
from typing import Final

from qgis_sdk import QgisSdkPlugin, describe
from qgis_sdk.core import PluginContext
from qgis_sdk.models import CrsInput, LayerInput, Metres, VectorLayerInfo
from qgis_sdk.processing.codegen import emit_typescript_module
from qgis_sdk.processing.snapshot import core_catalogue

from qgis_sdk_tools.generate import generate_schema_typescript
from qgis_sdk_tools.scaffold.options import PackageManager, ScaffoldOptions, WebOptions

from ._react import REACT_APP, REACT_TEST
from ._vanilla import REACT_MAIN, VANILLA_APP, VANILLA_TEST


def _plan_web_phase1(files, options, web):
    if web.framework == "react":
        files += [
            ("web/src/main.tsx", REACT_MAIN),
            ("web/src/App.tsx", REACT_APP.replace("{title}", options.title)),
            ("web/src/App.test.tsx", REACT_TEST),
        ]
    else:
        files += [
            ("web/src/main.ts", VANILLA_MAIN),
            ("web/src/app.ts", VANILLA_APP.replace("{title}", options.title)),
            ("web/src/app.test.ts", VANILLA_TEST),
        ]
    return tuple(files)


def _package_json_phase1(dependencies, dev_dependencies, options):
    package = {
        "name": f"{options.plugin}-web",
        "private": True,
        "version": options.version,
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "test": "vitest run",
            "typecheck": "tsc --noEmit",
            "bindings": f"cd .. && {bindings_command()}",
        },
        "dependencies": dict(sorted(dependencies.items())),
        "devDependencies": dict(sorted(dev_dependencies.items())),
    }
    return json.dumps(package, indent="\t") + LF


LF: Final = "\n"
SDK_NPM_PACKAGE: Final = "@archont561/qgis-sdk"
SDK_NPM_VERSION: Final = "0.8.0"
"""The published bridge this scaffold is written against, pinned exactly.

``automation/release.py stamp --scope typescript`` moves it with every bridge
release, so a tools release offers the newest bridge it was qualified with;
``WebOptions.sdk_dependency`` replaces it for a page inside this repository
(decision-41).
"""
UI_NPM_PACKAGE: Final = "@archont561/qgis-sdk-ui"
UI_NPM_VERSION: Final = "0.1.0"
"""The published web components the templates opt into, pinned exactly.

One import in ``main.ts`` registers the ``<qgis-*>`` elements (decision-47);
``automation/release.py stamp --scope ui`` moves the pin with every UI release and
``WebOptions.ui_dependency`` replaces it inside this repository.
"""
BROWSER_TARGET: Final = "chrome108"
WEB_TEMPLATE_VERSIONS: Final[dict[str, str]] = {
    "typescript": "7.0.2",
    "vite": "8.3.5",
    "vitest": "5.0.5",
    "happy-dom": "21.0.4",
    "react": "19.3.1",
    "react-dom": "19.3.1",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.2",
}
"""Exact versions the generated ``package.json`` pins (controlled templates)."""
WebFile = tuple[str, str]
"""A project-relative path and its content; ``generate`` wraps it."""


def install_command(package_manager: PackageManager) -> tuple[str, ...]:
    """The install step for one manager, run inside ``web/``."""
    return (package_manager, "install")


def script_command(package_manager: PackageManager, script: str) -> tuple[str, ...]:
    """How one manager runs a ``package.json`` script."""
    if package_manager == "pnpm":
        return ("pnpm", script)
    return (package_manager, "run", script)


def template_plugin_app(options: ScaffoldOptions) -> QgisSdkPlugin:
    """The declarations emitted by the starter plugin module."""
    app = QgisSdkPlugin(id=options.plugin, title=options.title)

    @app.action(id="ping", title="Ping")
    def ping(ctx: PluginContext, value: int) -> int:
        return value

    @app.action(id="project_layers", title="Project layers")
    def project_layers(ctx: PluginContext) -> list[str]:
        return []

    if options.algorithm:

        @app.action(id="buffer", title="Buffer a layer")
        def buffer(
            ctx: PluginContext,
            layer_id: LayerInput,
            distance_metres: Metres,
            working_crs: CrsInput,
        ) -> VectorLayerInfo:
            raise NotImplementedError("schema template only")

    if options.ui == "native":

        @app.action(id="open_ping", title="Open ping")
        def open_ping(ctx: PluginContext) -> None:
            pass

    return app


def plan_web(options: ScaffoldOptions) -> tuple[WebFile, ...]:
    """Every file under ``web/`` for ``options.web``; the page view is the runtime's."""
    web = options.web
    if web is None:
        return ()
    files: list[WebFile] = [
        ("web/package.json", _package_json(options, web)),
        ("web/vite.config.ts", _vite_config(options, web)),
        ("web/tsconfig.json", _tsconfig(web)),
        ("web/index.html", _index_html(options, web)),
        ("web/.gitignore", "node_modules/\n"),
        (
            "web/src/bridge.schema.ts",
            generate_schema_typescript(describe(template_plugin_app(options))),
        ),
        (
            "web/src/processing.schema.ts",
            emit_typescript_module(core_catalogue(), [SCAFFOLD_PROCESSING_PROVIDER]),
        ),
    ]
    return _plan_web_phase1(files, options, web)


SCAFFOLD_PROCESSING_PROVIDER: Final = "native"
BRIDGE_BINDINGS_COMMAND: Final = (
    "qgis-sdk bridge generate --out web/src/bridge.schema.ts --check"
)
PROCESSING_BINDINGS_COMMAND: Final = (
    f"qgis-sdk processing generate --provider {SCAFFOLD_PROCESSING_PROVIDER} "
    "--no-python --web-out web/src/processing.schema.ts --check"
)


def bindings_command() -> str:
    """The drift check the project's CI runs, from the project root.

    The plugin application comes from ``[tool.qgis-sdk] plugin`` in the project's
    ``pyproject.toml`` (decision-43), so the first command names only the
    output; the second reads the Processing registry of the project's QGIS
    install (decision-64).
    """
    return f"{BRIDGE_BINDINGS_COMMAND} && {PROCESSING_BINDINGS_COMMAND}"


def _package_json(options: ScaffoldOptions, web: WebOptions) -> str:
    react = web.framework == "react"
    dependencies: dict[str, str] = {
        SDK_NPM_PACKAGE: web.sdk_dependency or SDK_NPM_VERSION,
        UI_NPM_PACKAGE: web.ui_dependency or UI_NPM_VERSION,
    }
    dev_dependencies = {
        name: WEB_TEMPLATE_VERSIONS[name]
        for name in ("happy-dom", "typescript", "vite", "vitest")
    }
    if react:
        dependencies.update(
            react=WEB_TEMPLATE_VERSIONS["react"],
            **{"react-dom": WEB_TEMPLATE_VERSIONS["react-dom"]},
        )
        dev_dependencies.update(
            {
                name: WEB_TEMPLATE_VERSIONS[name]
                for name in ("@types/react", "@types/react-dom", "@vitejs/plugin-react")
            }
        )
    return _package_json_phase1(dependencies, dev_dependencies, options)


def _vite_config(options: ScaffoldOptions, web: WebOptions) -> str:
    react = web.framework == "react"
    imports = 'import { defineConfig } from "vitest/config";\n'
    plugins = ""
    if react:
        imports = 'import react from "@vitejs/plugin-react";\n' + imports
        plugins = "\tplugins: [react()],\n"
    return (
        f"{imports}\n"
        "// QGIS shows the page in Qt WebEngine, which is Chromium: Qt 6.5's is\n"
        "// Chromium 108. Raise the target together with qgisMinimumVersion, never\n"
        "// above what the oldest QGIS you support ships.\n"
        "export default defineConfig({\n"
        f"{plugins}"
        '\tbase: "./",\n'
        "\tbuild: {\n"
        f'\t\toutDir: "../{options.plugin}/web",\n'
        "\t\temptyOutDir: true,\n"
        f'\t\ttarget: "{BROWSER_TARGET}",\n'
        "\t},\n"
        "\ttest: {\n"
        '\t\tenvironment: "happy-dom",\n'
        "\t},\n"
        "});\n"
    )


def _tsconfig(web: WebOptions) -> str:
    compiler: dict[str, object] = {
        "target": "ES2022",
        "lib": ["ES2022", "DOM", "DOM.Iterable"],
        "module": "ESNext",
        "moduleResolution": "bundler",
        "types": ["vite/client"],
        "strict": True,
        "noEmit": True,
        "isolatedModules": True,
        "skipLibCheck": True,
    }
    if web.framework == "react":
        compiler["jsx"] = "react-jsx"
    return (
        json.dumps({"compilerOptions": compiler, "include": ["src"]}, indent="\t") + LF
    )


def _index_html(options: ScaffoldOptions, web: WebOptions) -> str:
    entry = "main.tsx" if web.framework == "react" else "main.ts"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "\t<head>\n"
        '\t\t<meta charset="utf-8" />\n'
        f"\t\t<title>{options.title}</title>\n"
        "\t\t<!-- Qt serves this inside QGIS; outside, the page notices it is missing. -->\n"
        '\t\t<script src="qrc:///qtwebchannel/qwebchannel.js"></script>\n'
        "\t</head>\n"
        "\t<body>\n"
        '\t\t<div id="app"></div>\n'
        f'\t\t<script type="module" src="/src/{entry}"></script>\n'
        "\t</body>\n"
        "</html>\n"
    )


VANILLA_MAIN = """import { QgisSdk } from "@archont561/qgis-sdk";
// The SDK's web components: this import registers every <qgis-*> element,
// the stylesheet styles them from the --qgis-sdk-* tokens applyHostTheme
// fills with the QGIS palette. Drop the three to go without.
import { applyHostTheme } from "@archont561/qgis-sdk-ui";
import "@archont561/qgis-sdk-ui/define";
import "@archont561/qgis-sdk-ui/style.css";
import { createApp } from "./app";
import schema from "./bridge.schema";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

// Three statements connect the page: the generated schema, the SDK built on
// it, the app. Outside a QGIS web view the SDK refuses at once, with the
// reason, instead of waiting for a channel that never comes.
try {
	const qgis = QgisSdk.fromBridgeSchema(schema);
	void applyHostTheme(qgis);
	createApp(root, qgis);
} catch (failure: unknown) {
	root.textContent =
		failure instanceof Error
			? `${failure.message}. Open this page from QGIS: outside a QGIS web view there is no host to talk to.`
			: String(failure);
}
"""
