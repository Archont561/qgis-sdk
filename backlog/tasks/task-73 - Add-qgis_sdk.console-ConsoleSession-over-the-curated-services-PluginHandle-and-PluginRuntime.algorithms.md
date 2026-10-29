---
id: TASK-73
title: >-
  Add qgis_sdk.console: ConsoleSession over the curated services, PluginHandle
  and PluginRuntime.algorithms
status: Done
assignee: []
created_date: '2026-10-26T09:30:00Z'
updated_date: '2026-10-29T18:10:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-63
  - TASK-64
type: enhancement
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-48. qgis_sdk.console.connect(iface=None, settings_prefix='console', notifications=None) -> ConsoleSession built with native_plugin_context over qgis.utils.iface; session.ctx is the same PluginContext a plugin gets (layers, project, settings, styles, algorithms, network, notifications, desktop); session.plugin(name) -> PluginHandle over qgis.utils.plugins[name].runtime with description, actions, streams, algorithms, state, run(action_id, **inputs), open(action_id), reload() (dev only); DesktopLifecycleAdapter.console() returns a session bound to that plugin's context; PluginRuntime.algorithms lists the registered Processing ids; sessions own a ResourceScope and close explicitly or with the plugin. No iface proxy; iface stays behind ctx.desktop.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 connect() without QGIS Desktop (standalone QgsApplication) yields a context whose desktop capability refuses by name and whose other services work; with an iface it exposes ctx.desktop; close() disposes everything the session started and a second close is a no-op (pure tests on fakes + qgis native tests).
- [x] #2 PluginHandle.run validates inputs exactly as the bridge dispatcher does and raises the same QgisSdk errors; open() opens the declared form or named surface on the GUI thread; algorithms lists the provider ids TASK-63 registers; attributes missing on an older vendored runtime refuse by name (native tests under the desktop harness, QGIS_SDK_DESKTOP_ADAPTER=1).
- [x] #3 plugins[name].console() on a built, vendored plugin returns a working session sharing the plugin's service instances (build-install harness); qgis-sdk dev prints the console recipe; doc-12 gains a 'From the QGIS Python console' section with both routes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Re-scoped 2026-10-27 from m-6 (0.7.0) to m-7 (0.8.0): the console session is an access surface over the same curated services the plugin HTTP API reaches, it blocks nothing in m-6 and nothing in m-6 blocks it, and 0.7.0 ships what is already qualified. Lands in m-7 sprint 2.

Session follow-up: TASK-125 explores validated plugin-to-plugin actions. The console PluginHandle does not by itself authorize cross-plugin calls; avoid concrete isinstance checks across separately vendored SDK copies.

Landed in the m-7 sprint-2 train:

- `qgis_sdk/console.py` is pure to import (PyQGIS only inside the functions that need it): `connect()`, `bind(adapter)`, `dev_session()`, `ConsoleSession`, `PluginHandle`, `ConsoleError` (`console_refused`). A handle reads the object QGIS holds (`adapter.runtime`, `.context`, `.bindings`, `.surfaces`) by attribute, so a plugin built by an older SDK copy works while it has them and refuses by name for the rest - no `isinstance` crosses a vendored copy.
- `PluginRuntime.algorithms` returns `provider:algorithm` while the registry advertises the plugin's providers and `()` before `start()`/after `unload()`/without `processing`; `DEV_REQUEST_ENV` and `dev_request()` now live in `qgis_sdk.environment` (the devtools `REQUEST_ENV` aliases it, so the marker has one name).
- `DesktopLifecycleAdapter.console()` (and `DesktopHost.console()`) returns a session bound to that plugin's context; the adapter closes its sessions on `unload()`, so a plugin's own teardown closes them and `session.close()` never stops the plugin.
- `qgis-sdk dev` prints the two-line console recipe with the plugin's name; doc-12 gains "From the QGIS Python console" with both routes.
- Evidence: 24 pure tests (`test_console_pure.py`) over a monkeypatched `qgis.utils.plugins` mapping, 5 native tests (`test_console_native.py`, `qgis` layer) over a real `classFactory`/`initGui`/`qgis.utils.plugins` entry - real layers, real `iface`, a real dialog opened through the plugin's own `SurfaceHost`, `scaffold_demo:buffer`-style ids - and the built-and-installed harness (`scaffold_desktop_smoke`) now proves `plugins[name].console()` on a generated, vendored plugin: `console_context_shared`, `console_actions`, `console_algorithms`, `console_action_result` and `console_closed` are report fields and `passed` requires them.
- AC2's `QGIS_SDK_DESKTOP_ADAPTER` naming is stale (that variable exists nowhere in the tree since the smoke suite replaced it): the native half runs under the `qgis` layer here and the Desktop half under `scaffold_desktop_smoke` (`pytest -m smoke`), which is where a real `iface` exists.
<!-- SECTION:NOTES:END -->
