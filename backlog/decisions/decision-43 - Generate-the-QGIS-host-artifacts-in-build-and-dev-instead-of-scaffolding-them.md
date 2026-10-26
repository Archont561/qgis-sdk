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
   `BrowserPolicy`/`Dispatcher` wiring `webview.py` had. A plugin that needs a
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
