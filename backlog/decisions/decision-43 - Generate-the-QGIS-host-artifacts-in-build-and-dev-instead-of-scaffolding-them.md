---
id: decision-43
title: Generate the QGIS host artifacts in build and dev instead of scaffolding them
date: '2026-10-26 14:10'
status: accepted
---
## Context

`qgis-sdk new` writes, next to the one file an author should read
(`<plugin>/plugin.py`), four that exist only because QGIS's plugin loader needs
them: `metadata.txt` (QGIS reads `[general]` before importing anything),
`__init__.py` with `classFactory(iface)`, a `Desktop` wrapper class that adds
one toolbar button and opens the page, and `webview.py`, which builds the
restricted `QWebEngineView` over the plugin's dispatcher. `plugin.py` itself
carries `build_context(iface)`, choosing between the native and the bare
context, and a `MessageBarNotifications` class. None of this is the plugin;
all of it is how one host loads a plugin, and all of it is identical from one
scaffold to the next except for a handful of names. The author is nevertheless
the one who owns it: it is in their package, their tests import it, and a
change to the SDK's host glue reaches them only through a new scaffold.

`qgis-sdk build` already stages a copy of the package and vendors the runtime
into it; `qgis-sdk dev` already decides what `QGIS_PLUGINPATH` points at. Both
are the moment the host-specific shape is actually needed.

## Decision

1. **The source tree holds the plugin, not the host adapter.** A project is
   `pyproject.toml`, the package with `plugin.py` (and whatever the author
   adds), `tests/` and optionally `web/`. The package `__init__.py` is the
   author's and may be empty. `pyproject.toml` names the entry once:

   ```toml
   [tool.qgis-sdk]
   plugin = "field_tools.plugin:FieldTools"
   qgis-minimum-version = "3.40"

   [tool.qgis-sdk.web]      # only with a page
   placement = "dock"
   grants = ["project.read", "layers.read"]   # curated host operations the page may call
   ```

2. **`metadata.txt` is rendered, never authored.** `build` and `dev` write it
   from `[project]` (`version`, `description`, the first author's name and
   email) and the plugin class (`name` from its `title`,
   `hasProcessingProvider` from `providers`, decision-42) plus
   `[tool.qgis-sdk]` (`qgis-minimum-version`, `experimental`, and a
   `[tool.qgis-sdk.metadata]` table passed through for the optional QGIS keys:
   `homepage`, `tracker`, `repository`, `tags`, `category`, `icon`,
   `changelog`). An authored `metadata.txt` is a `META001` finding - two
   sources of truth - with the remediation of moving its keys.
3. **`classFactory` comes from the runtime.** `qgis_sdk.adapters.desktop.host(
   "field_tools.plugin:FieldTools")` returns the `classFactory` QGIS calls. The
   returned lifecycle does what the generated wrapper did: build the context
   (native when a `QgsApplication` runs, bare otherwise, with message-bar
   notifications when an `iface` exists), start the `PluginRuntime`, register
   the providers, and - when `[tool.qgis-sdk.web]` is present - add the toolbar
   action and open the page in a dialog or dock under the same
   `BrowserPolicy`/`Dispatcher` wiring `webview.py` had, with the curated
   host operations whose grants `[tool.qgis-sdk.web] grants` lists registered
   on that dispatcher (`register_host_operations(..., only=)`, decision-27);
   an unknown grant is a `check` finding. A plugin that needs a
   different context declares `context_factory` as a class attribute.
   `build` appends `classFactory = host(...)` to the **staged** copy of
   `__init__.py`; `check` reports an authored `classFactory` (`ENTRY002`) so a
   project cannot drift into two.
4. **`dev` loads source through a generated host package.** It writes
   `.qgis-sdk/dev/host/<plugin>/__init__.py` and `metadata.txt`; that
   `__init__.py` extends its `__path__` with the source package directory,
   executes the author's `__init__.py` in its namespace, and binds
   `classFactory`. `QGIS_PLUGINPATH` points at `.qgis-sdk/dev/host`, so QGIS
   imports the host package while every module under it resolves from the
   author's tree, and reload-on-save keeps dropping the same module names.
   `dev --mode standalone` and `qgis-sdk test --target desktop` run through the
   same `host()`.
5. **The starter tests drive the runtime, not the host.**
   `tests/test_plugin.py` builds a `PluginRuntime` over the SDK fakes (the
   `qgis_sdk.testing` helpers) and calls the declared actions and algorithms
   directly; nothing in a scaffolded test imports a host artifact.

## Consequences

- `qgis-sdk new` output shrinks to `pyproject.toml`, `README.md`,
  `.gitignore`, `<plugin>/__init__.py`, `<plugin>/plugin.py`,
  `tests/test_plugin.py` and, with `--web`, the `web/` app. `webview.py`,
  `metadata.txt`, the `Desktop` wrapper, `build_context` and
  `MessageBarNotifications` leave the templates and live in
  `qgis_sdk.adapters.desktop` (and `adapters.webengine`) under the SDK's own
  tests.
- `check`'s `META00x` rules read `pyproject.toml` instead of `metadata.txt`;
  the build's `ENTRY001` ("`__init__.py` binds `classFactory`") inverts into
  the staged-copy guarantee plus `ENTRY002`. Projects scaffolded before this
  decision get one finding per leftover artifact, each naming what to delete.
- An existing project migrates by deleting four files and adding five lines
  of TOML; the plugin class does not change. doc-12's migration notes carry
  the list.
- A fix in the host glue now ships with the runtime, so every installed
  plugin gets it on its next `build`, and the opt-in harnesses prove it once
  instead of per scaffold.
- decision-12 (one controller per UI surface) is narrowed in practice: the
  runtime's page view is the first surface it owns, configured rather than
  authored; the controller API it describes remains proposed.
- The bundle still vendors the runtime, so an installed plugin needs no
  `qgis-sdk` on the host; `metadata.txt` in the ZIP is byte-identical between
  `build` and `dev` for the same source.

## Amendment (2026-10-26): the runtime is detected from the project's dependencies

Owner's ruling after the question "does `build` ask for the runtime?": it
does not, and it must not grow a `[tool.qgis-sdk] runtime = ...` field
either. **The project's ordinary dependency declaration is the source of
truth**, and the tools detect the runtime from it:

- `qgis-sdk new` writes `[project] dependencies = ["qgis-sdk-runtime>=X.Y,<X.Y+1"]`
  with the range derived from the runtime installed where `new` runs
  (`importlib.metadata`), never from a template literal, plus
  `[dependency-groups] dev = ["qgis-sdk-tools>=X.Y,<X.Y+1"]` so a fresh
  clone can `pip install --group dev` and get the matching `qgis-sdk`
  command. A bare checkout with no installed distribution writes the
  checkout's own version.
- `check` already reads every requirement string in `[project]
  dependencies`, `optional-dependencies` and `dependency-groups`
  (VERSION001, TASK-9). It gains VERSION003: the project declares no
  `qgis-sdk-runtime` (or `qgis-sdk`) requirement at all, with the
  remediation naming the line to add; a 0.5 project migrating therefore gets
  told once.
- `build` and `dev` resolve the runtime by that requirement: the `qgis_sdk`
  importable next to the tools must satisfy the declared specifier, otherwise
  the command refuses with VERSION004 (declared vs. installed, and the
  `pip install` line that would satisfy it) instead of silently vendoring a
  runtime the author did not ask for. The tools never install anything
  themselves. The ZIP notice records both the declared requirement and the
  resolved version. A project with no declaration builds against the
  installed runtime, with VERSION003 in the build output, so existing
  projects keep building.
- The vendoring itself is unchanged: the resolved runtime is copied under
  `<plugin>/_vendor/qgis_sdk`; the end user's QGIS installs nothing.

Carried by TASK-65 (scaffold lines) and TASK-64 (resolution and the two
rules).


## Status review (2026-10-26, TASK-64): implemented, with two refinements

Shipped by TASK-64 (runtime `host()`/`webview`, tools `project.py`/`artifacts.py`,
rules `PROJECT002`/`CONFIG001`/`META001`/`META002`/`ENTRY002`/`GRANT001`/
`VERSION003`/`VERSION004`, the scaffold and `examples/simple` migrated). Two
points were settled in the implementation and differ from, or sharpen, the text
above:

- **Grants are grants *or* operation ids.** `[tool.qgis-sdk.web] grants` accepts
  the catalogue's grant names (`layers.read` selects `layers.list` and
  `layers.get`) and single operation ids (`project.layer_ids`);
  `qgis_sdk.bridge.host.granted_operations` resolves either to the ids
  `register_host_operations(only=...)` takes, and anything else is `GRANT001`.
  The Decision's example (`grants = ["project.read", "layers.read"]`) is
  therefore valid as written.
- **The starter tests go through `host()`.** Point 5 said the starter tests
  "never import a host artifact"; `tests/test_plugin.py` instead binds
  `classFactory = host("<pkg>.plugin:<Class>", placement=...)` and drives
  `initGui()`/`unload()`, because `host()` without a `QgsApplication` *is* the
  bare runtime over the fakes and running the same factory QGIS runs is the
  better evidence. `host()` resolves the plugin module through the builtin
  `__import__` so QGIS's own module tracking drops it on unload.
- `qgis-sdk test --target desktop` stages the same host package `dev` does, and
  the pytest plugin makes `import <plugin>` resolve to it inside the Desktop
  run, so the plugin is loaded exactly as QGIS loads it.
