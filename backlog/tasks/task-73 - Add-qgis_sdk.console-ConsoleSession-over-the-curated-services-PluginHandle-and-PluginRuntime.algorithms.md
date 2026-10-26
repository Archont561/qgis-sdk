---
id: TASK-73
title: >-
  Add qgis_sdk.console: ConsoleSession over the curated services, PluginHandle
  and PluginRuntime.algorithms
status: To Do
assignee: []
created_date: '2026-10-26T09:30:00Z'
labels: []
milestone: m-6
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
- [ ] #1 connect() without QGIS Desktop (standalone QgsApplication) yields a context whose desktop capability refuses by name and whose other services work; with an iface it exposes ctx.desktop; close() disposes everything the session started and a second close is a no-op (pure tests on fakes + qgis native tests).
- [ ] #2 PluginHandle.run validates inputs exactly as the bridge dispatcher does and raises the same QgisSdk errors; open() opens the declared form or named surface on the GUI thread; algorithms lists the provider ids TASK-63 registers; attributes missing on an older vendored runtime refuse by name (native tests under the desktop harness, QGIS_SDK_DESKTOP_ADAPTER=1).
- [ ] #3 plugins[name].console() on a built, vendored plugin returns a working session sharing the plugin's service instances (build-install harness); qgis-sdk dev prints the console recipe; doc-12 gains a 'From the QGIS Python console' section with both routes.
<!-- AC:END -->
