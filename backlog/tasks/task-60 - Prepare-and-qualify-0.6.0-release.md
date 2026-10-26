---
id: TASK-60
title: Prepare and qualify 0.6.0 release
status: To Do
assignee: []
created_date: '2026-10-25 23:27'
updated_date: '2026-10-26 07:50'
labels: []
milestone: m-5
dependencies:
  - TASK-58
  - TASK-59
  - TASK-31
  - TASK-61
priority: high
type: chore
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. 0.6.0 is the API-ergonomics minor (m-5): function-form @job (decision-38, TASK-58) and capability attributes replacing require_<name>() (decision-39, TASK-59), both already on main with doc-12 migration notes. The bridge joined the milestone with TASK-61 (decision-40: root entry barrel, prefixed generated contract errors; wire unchanged), so 0.6.0 is a pair: Python 0.6.0 and @archont561/qgis-sdk 0.4.0. Verify the milestone work with the 0.5.0 gate re-run over the new API plus the bridge gate and obtain explicit release authorization; stamp, tag (python-v0.6.0 and ts-v0.4.0 on the merge commit) and publish only on that authorization, with an -rc.N dry run first if asked.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.6.0 work has verified outcomes and relevant test/artifact evidence: Python suite, tests/scripts, the example project and the opt-in harnesses the two changes touched are green on the gate commit; the doc-12 0.6.0 migration note names every removed or renamed symbol.
- [ ] #2 Use valid SemVer and prereleases such as 0.6.0-rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves to >=0.6.0,<0.7) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a 0.5-style project reports the API changes rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge pair is confirmed with evidence: @archont561/qgis-sdk 0.4.0 (TASK-61, decision-40) is gated with the same run - Bun tests, typecheck, Biome, release.py verify-versions agreeing on contract version 1 in both languages - and stamped and tagged ts-v0.4.0 on the same merge commit only on the same explicit authorization; HOST_FINGERPRINT, HOST_SCHEMA_VERSION and BRIDGE_PROTOCOL_VERSION are shown unchanged since ts-v0.3.0, and the record states that bridge 0.4.0 ran against the 0.6.0 runtime.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
decision-41 (TASK-62): release.py stamp --scope typescript now also rewrites SDK_NPM_VERSION in qgis_sdk_tools/scaffold/web.py, so the ts-v0.4.0 stamp moves the scaffold's bridge pin to 0.4.0 in the same commit; verify-versions reports it as the scaffold pin. Once that pin names 0.4.0, the scaffold templates may import from the root barrel instead of ./bridge.
<!-- SECTION:NOTES:END -->
