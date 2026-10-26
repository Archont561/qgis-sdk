---
id: TASK-64
title: 'Generate metadata.txt, classFactory and the page view in build and dev'
status: To Do
assignee: []
created_date: '2026-10-26T08:27:00Z'
updated_date: '2026-10-26 14:52'
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
- [x] #1 qgis-sdk build on a project without metadata.txt, classFactory or webview.py produces a ZIP whose metadata.txt holds every key QGIS requires, hasProcessingProvider matching providers, and whose <plugin>/__init__.py binds classFactory via host(); the source tree is untouched; pure tests cover the rendering and the append, ENTRY002 and the pyproject META00x rules.
- [x] #2 host(spec) under a headless QgsApplication starts and unloads the plugin, registers its providers, and with [tool.qgis-sdk.web] opens the built page in a QWebEngineView as dock or dialog and answers a ping over QWebChannel (webengine test); without a QgsApplication it builds the bare context and refuses ctx.desktop by name.
- [x] #3 qgis-sdk dev loads the source plugin through the generated host package: edit, reload and unload work as before (QGIS_SDK_HEADLESS_LIFECYCLE / QGIS_SDK_DESKTOP_ADAPTER harnesses and the reloader tests), dev --mode standalone and test --target desktop go through host(), and the dev host directory is gitignored by the scaffold.
- [x] #4 doc-12 documents [tool.qgis-sdk], the generated artifacts, the check rules and the migration (delete four files, add the TOML); decision-12 gets a status review naming the runtime page view as the first owned surface.
- [x] #5 [tool.qgis-sdk.web] grants = [...] selects the curated host operations host() registers on the page's dispatcher via register_host_operations(only=); no grants registers none; an unknown grant is a check finding; the webengine test calls a granted and a non-granted host operation from the page.
- [x] #6 build and dev resolve the runtime from the project's own requirement on qgis-sdk-runtime / qgis-sdk (decision-43 amendment): the importable runtime must satisfy the declared specifier or the command refuses with VERSION004 naming declared vs. installed; a project with no declaration gets VERSION003 and builds against the installed runtime; the ZIP notice records the requirement and the resolved version; the tools never install anything (pure tests on fake metadata, build-install harness).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: AC 6 added - runtime autodetected from the project's dependencies, never from a dedicated field.

Implemented 2026-10-26 (sprint 3 of doc-18), Done on merge. Runtime: qgis_sdk.adapters.desktop rewritten around resolve_plugin_spec (builtin __import__ so QGIS's module tracking sees it), DesktopHost, host(spec, *, placement, grants), default_context (native under QgsApplication, bare otherwise, MessageBarNotifications with an iface), QgisSdkHostError; create_class_factory retained. New qgis_sdk.adapters.webview.open_view/close_view/add_toolbar_action/dev_server own the QWebEngineView over BrowserPolicy + Dispatcher + QWebChannel ('bridge' object), as a QDialog or a QDockWidget named by the view id. qgis_sdk.bridge.host.granted_operations resolves grant names (layers.read) or operation ids (project.layer_ids) to the ids register_host_operations(only=) takes. Tools: qgis_sdk_tools.project (ProjectConfig/WebConfig, load_project/require_project; PROJECT002, CONFIG001, META002, GRANT001), qgis_sdk_tools.artifacts (introspect_plugin, render_metadata, class_factory_source, render_dev_host_init, write_dev_host under .qgis-sdk/dev/host/<plugin>/), check.project META001/ENTRY002, check.versions VERSION003/VERSION004, bundle stages metadata.txt + appends classFactory = host(...) to the staged __init__.py and records requirement + resolved runtime in the NOTICE; dev / dev --mode standalone / test --target desktop go through the host package (pytest plugin _HostFirst finder). Scaffold writes the clean project (pyproject with [tool.qgis-sdk], empty __init__.py, plugin.py, tests/test_plugin.py, optional web/; runtime/tools windows from importlib.metadata); examples/simple migrated (metadata.txt, webview.py, classFactory, build_context, MessageBarNotifications removed; dialogs.py added). Evidence: Python suite 1579 passed / 43 skipped; tests/scripts 241; opt-in harnesses REFERENCE 5, DEVTOOLS 9, SCAFFOLD_WEB 8, SCAFFOLD_DESKTOP 10, HEADLESS_LIFECYCLE 5, DESKTOP_ADAPTER 22, BUILD_INSTALL 1; new tests test_desktop_host.py (13 pure) and test_desktop_host_native.py (4 webengine: ping, granted vs non-granted host op, dock/dialog, unload). Docs: doc-12 (Desktop host, scaffold, check rules, dev, build, 0.6.0 'Project shape' migration), decision-43 and decision-12 status reviews, doc-18 sprint 3/4 re-slice. Left to TASK-65: release.py stamp moving the example's literal >=0.5,<0.6 windows, doc-13 and the remaining guides, coexistence harness onto host(), Python-side scaffold-vs-example equality test.
<!-- SECTION:NOTES:END -->
