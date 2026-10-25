---
id: TASK-59
title: Expose optional context services as capability attributes that refuse by name
status: In Progress
assignee: []
created_date: '2026-10-25 22:43'
updated_date: '2026-10-25 22:43'
labels: []
dependencies: []
type: enhancement
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User request on 2026-10-25 (follow-up to TASK-58): hide the require_*() accessors. decision-39 fixes the shape: on PluginContext, UiContext, AlgorithmContext and JobContext every optional service (desktop, network, layers, project, settings, styles, algorithms, workers) is a Capability attribute typed as the service whose read checks the scope and raises QgisSdkUnsupportedCapabilityError(name) when the host did not provide it; ctx.has(name) / ctx.capabilities are the probes; require_*() is removed (breaking, 0.6.0 of qgis-sdk-runtime). Amends decision-32.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Reading an absent capability on any of the four contexts raises QgisSdkUnsupportedCapabilityError naming it; a provided one is the very instance the host passed; a read on a closed scope raises QgisSdkScopeClosedError; no context exposes a require_* attribute.
- [ ] #2 ctx.has(name) answers without touching the scope, raises ValueError for a name the context does not carry, and ctx.capabilities lists what was provided; constructors keep their keyword arguments and contexts stay immutable.
- [ ] #3 Runtime (HostServices.from_context, native_plugin_context), tools (scaffold, devtools exercise), examples/simple, every test and every guide use the attribute form; the Python suite, tests/scripts and the affected opt-in harnesses pass.
- [ ] #4 decision-39 recorded, decision-32 carries the amended-by note, doc-12 Pure contract layer updated and the 0.6.0 migration note lists the renames.
<!-- AC:END -->
