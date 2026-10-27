---
id: TASK-32
title: Prepare and qualify 0.7.0 release
status: To Do
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-27T19:00:00Z'
labels: []
milestone: m-6
dependencies:
  - TASK-60
  - TASK-68
  - TASK-96
  - TASK-69
  - TASK-70
  - TASK-43
  - TASK-108
  - TASK-109
  - TASK-110
references:
  - doc-8
priority: medium
type: chore
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the UI toolkit release (m-6, decision-46), not evidence of release or permission to publish. Re-pointed on 2026-10-26: 0.7.0 was the tentative native-compute reservation (now m-7 / 0.8.0, TASK-71) and becomes the release of the parameter kinds, standard surfaces, headless web bindings, Storybook and themed defaults, paired with the bridge minor that carries ./react additions and ./ui. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.7.0 work (TASK-68, TASK-69, TASK-96, TASK-70, TASK-108, TASK-109, TASK-110, TASK-43) has verified outcomes and test/artifact evidence: Python suite, tests/scripts, the example, the scaffold-web and reference harnesses, Storybook build; the doc-12/doc-13 0.7.0 migration notes cover every added or renamed name.
- [ ] #2 Use valid SemVer and prereleases such as 0.7.0-rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a 0.6 project reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge pair becomes a triple and is confirmed with evidence: the next @archont561/qgis-sdk minor (store core, ./vue and ./svelte adapters) and the first @archont561/qgis-sdk-ui release are gated with the same run - Bun tests across every adapter's Vitest project, typecheck, Biome, Storybook build, release.py verify-versions agreeing on the contract version in both languages and on the UI package's bridge peer range - and stamped and tagged (ts-v*, ui-v*) on the same merge commit only on the same explicit authorization; HOST_FINGERPRINT, HOST_SCHEMA_VERSION and BRIDGE_PROTOCOL_VERSION are shown unchanged, and the record states that both packages ran against the 0.7.0 runtime.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: AC 5 rewritten for decision-47 - the gate now covers three artifacts (Python, bridge, qgis-sdk-ui).

2026-10-27: TASK-73 and TASK-77 re-scoped to m-7 (see m-6); the gate no longer waits on them. TASK-108, TASK-109 and TASK-110 landed in this milestone and are added as dependencies so AC #1's evidence list is complete.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-26 09:05
---
Rewritten on 2026-10-26: this task kept its id and the 0.7.0 number but changed meaning. 0.7.0 is now the UI toolkit release (m-6 renamed in place, decision-46), so the title, description, dependencies and all five ACs were replaced; the old tentative-native-compute gate moved to TASK-71 in m-7 (0.8.0) with the previous ACs copied verbatim. The comments below describe the earlier scope and are kept as history.
---

author: qgis-sdk agent
created: 2026-10-24 19:10
---
AC #5 was added on 2026-10-24 to carry the bridge obligation the then-m-6, now [m-12](../milestones/m-12%20-%201.1.0-%E2%80%94-deferred-native-compute-feasibility-(tenta.md) already states: a native backend changes what runs behind Python, not what crosses `QWebChannel`, so this milestone expects no bridge release at all - and the milestone requires that expectation to be re-checked rather than repeated. Deferred or not, the gate has to be able to say "nothing crossed" with evidence. No criterion had been checked.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->
