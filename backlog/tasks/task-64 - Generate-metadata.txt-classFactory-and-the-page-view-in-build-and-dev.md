---
id: TASK-64
title: Generate metadata.txt, classFactory and the page view in build and dev
status: To Do
assignee: []
created_date: '2026-10-26T08:27:00Z'
updated_date: '2026-10-26T08:48:00Z'
labels: []
milestone: m-5
dependencies:
  - TASK-63
type: enhancement
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-43. pyproject.toml [tool.qgis-sdk] plugin = "pkg.module:Class" is the single entry declaration; build and dev render metadata.txt from [project], the plugin class (name from title, hasProcessingProvider from providers) and [tool.qgis-sdk] (qgis-minimum-version, experimental, a passthrough metadata table). qgis_sdk.adapters.desktop.host(spec) returns the classFactory: default context (native under a QgsApplication, bare otherwise, message-bar notifications with an iface; a context_factory class attribute overrides), PluginRuntime start/unload, provider registration, and with [tool.qgis-sdk.web] the toolbar action plus the dialog/dock page view that webview.py built. build appends classFactory = host(...) to the staged __init__.py; dev writes .qgis-sdk/dev/host/<plugin>/ whose __init__.py extends __path__ to the source package, executes the author's __init__.py and binds classFactory, and points QGIS_PLUGINPATH there. check: META00x read pyproject.toml, an authored metadata.txt is META001, an authored classFactory is ENTRY002.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 qgis-sdk build on a project without metadata.txt, classFactory or webview.py produces a ZIP whose metadata.txt holds every key QGIS requires, hasProcessingProvider matching providers, and whose <plugin>/__init__.py binds classFactory via host(); the source tree is untouched; pure tests cover the rendering and the append, ENTRY002 and the pyproject META00x rules.
- [ ] #2 host(spec) under a headless QgsApplication starts and unloads the plugin, registers its providers, and with [tool.qgis-sdk.web] opens the built page in a QWebEngineView as dock or dialog and answers a ping over QWebChannel (webengine test); without a QgsApplication it builds the bare context and refuses ctx.desktop by name.
- [ ] #3 qgis-sdk dev loads the source plugin through the generated host package: edit, reload and unload work as before (QGIS_SDK_HEADLESS_LIFECYCLE / QGIS_SDK_DESKTOP_ADAPTER harnesses and the reloader tests), dev --mode standalone and test --target desktop go through host(), and the dev host directory is gitignored by the scaffold.
- [ ] #4 doc-12 documents [tool.qgis-sdk], the generated artifacts, the check rules and the migration (delete four files, add the TOML); decision-12 gets a status review naming the runtime page view as the first owned surface.
- [ ] #5 [tool.qgis-sdk.web] grants = [...] selects the curated host operations host() registers on the page's dispatcher via register_host_operations(only=); no grants registers none; an unknown grant is a check finding; the webengine test calls a granted and a non-granted host operation from the page.
<!-- AC:END -->
