---
id: TASK-59
title: Expose optional context services as capability attributes that refuse by name
status: Done
assignee: []
created_date: '2026-10-25 22:43'
updated_date: '2026-10-25 23:26'
labels: []
milestone: m-5
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
- [x] #1 Reading an absent capability on any of the four contexts raises QgisSdkUnsupportedCapabilityError naming it; a provided one is the very instance the host passed; a read on a closed scope raises QgisSdkScopeClosedError; no context exposes a require_* attribute.
- [x] #2 ctx.has(name) answers without touching the scope, raises ValueError for a name the context does not carry, and ctx.capabilities lists what was provided; constructors keep their keyword arguments and contexts stay immutable.
- [x] #3 Runtime (HostServices.from_context, native_plugin_context), tools (scaffold, devtools exercise), examples/simple, every test and every guide use the attribute form; the Python suite, tests/scripts and the affected opt-in harnesses pass.
- [x] #4 decision-39 recorded, decision-32 carries the amended-by note, doc-12 Pure contract layer updated and the 0.6.0 migration note lists the renames.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered on PR #87 (commit 43411d8): Capability descriptors on all four contexts, has()/capabilities probes, require_*() removed; decision-39 + decision-32 amended-by note, doc-12 Pure contract layer and 0.6.0 migration note. Validation: lint/format clean, Python suite 1473 passed / 42 skipped, tests/scripts 226, test-reference-example 17+4, opt-in harnesses native services 133 / devtools 9 / reference 5 / desktop-adapter, scaffold-desktop and headless-smoke qualification runs green; CI run 40241839684 green (checks, cross-platform windows/macos).
<!-- SECTION:NOTES:END -->
