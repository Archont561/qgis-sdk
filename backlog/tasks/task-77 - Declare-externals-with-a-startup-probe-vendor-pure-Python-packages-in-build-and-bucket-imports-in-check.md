---
id: TASK-77
title: >-
  Declare externals with a startup probe, vendor pure-Python packages in build,
  and bucket imports in check
status: To Do
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-28 15:59'
labels: []
milestone: m-7
dependencies:
  - TASK-64
type: enhancement
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-50. [tool.qgis-sdk.build] external accepts tables {import, requirement, reason}; the generated classFactory probes externals before constructing the plugin and shows one message-bar error with the host-specific install hint on failure, leaving the plugin cleanly unloaded; externals are rendered into the generated metadata.txt description. [tool.qgis-sdk.build] vendor = [...] copies installed pure-Python distributions under <plugin>/_vendor/ with the import rewrite, records name/version in the notice and licenses under _vendor/LICENSES/; compiled extensions are refused with DEP003, missing transitive dependencies with DEP004. check buckets every import (stdlib, host, runtime, plugin, vendored, external, unknown) and reports unknown ones as DEP001 at check time. The SDK still installs nothing on the user's machine.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A missing external yields the message-bar error naming the package and the hint for the detected host, and the plugin is not half-initialised (qgis native test); the externals appear in the generated metadata.txt (pure test).
- [ ] #2 build vendors a pure-Python distribution with its license and rewritten imports and the plugin imports it from the ZIP; a compiled distribution is refused with DEP003 and a missing transitive dependency with DEP004 (pure tests on fixture distributions; build-install harness for one vendored package).
- [ ] #3 check prints each import's bucket and reports DEP001 with both exits before any build; doc-12 states that pandas-class packages are externals with a probe, never vendored.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Re-scoped 2026-10-27 from m-6 (0.7.0) to m-7 (0.8.0): externals and pure-Python vendoring are a build feature with no UI-toolkit dependency; it blocks nothing in m-6 and nothing in m-6 blocks it, and 0.7.0 ships what is already qualified. Lands in m-7 as its own small pull request before the gate.

Session follow-up: the owner requested an opt-in, end-user-approved dependency installation option. TASK-123 is a policy spike only; decision-50 remains in force and TASK-77 must not install packages unless a later decision explicitly revises that policy.
<!-- SECTION:NOTES:END -->
