---
id: TASK-137
title: Expose declaration descriptions as diagnostic JSON from the CLI
status: To Do
assignee: []
created_date: '2026-10-28 16:43'
labels: []
dependencies: []
references:
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_describe.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_descriptions.py
  - packages/qgis-sdk-tools/src/qgis_sdk_tools/_commands/_bridge.py
priority: medium
type: enhancement
ordinal: 137000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provide a discoverable qgis-sdk describe command for diagnosing what the unified qgis_sdk.describe(target) and target.describe() see. Accept a configured plugin and an explicit supported declaration target using a documented import specification. Emit machine-readable JSON suitable for inspection and tooling. The current API returns description objects rather than universally returning JSON: not every kind has to_json and existing bridge to_dict intentionally omits UI bindings and wires. Design a separate unified diagnostic representation instead of silently changing the bridge contract. Coordinate with TASK-120 and the planned diagnose bundle in TASK-106; no release milestone is assigned.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Document and implement target selection for a configured project plugin and explicitly named supported declarations; report invalid targets or imports clearly with a nonzero exit and no mixed diagnostic text on JSON stdout.
- [ ] #2 Provide a deterministic versioned JSON representation for every supported describe kind including combined action and surface bindings and handler wires where applicable; specify fields and serialization behavior for each kind.
- [ ] #3 Reuse the shared describe implementation without invoking action handlers or constructing surfaces; preserve existing Python description behavior and bridge wire serialization and compatibility.
- [ ] #4 Document that importing author modules and resolving annotations executes trusted Python and is not a sandbox; do not claim the command can safely inspect untrusted code.
- [ ] #5 Test supported target kinds and stacked bindings plus reproducible JSON and error paths and QGIS-free operation where supported; provide concise diagnostic examples and coordinate any future diagnose bundle integration.
<!-- AC:END -->
