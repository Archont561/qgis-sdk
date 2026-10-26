---
id: TASK-78
title: Prepare and qualify 0.8.0 release
status: To Do
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-26T10:02:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-32
  - TASK-74
  - TASK-75
  - TASK-76
  - TASK-79
type: chore
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the agent-access release (m-7, decision-49), not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization. Python-only release: runtime (loopback transport), tools (mcp extra, dev --agent, user-mode generation); the bridge is expected unchanged and that expectation is confirmed, not assumed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.8.0 work (TASK-74, 75, 76) has verified outcomes and test/artifact evidence: Python suite with the mcp extra, tests/scripts, the devtools and build-install harnesses, the scripted MCP client against both modes; doc-12 migration notes cover every added name and the security model.
- [ ] #2 Use valid SemVer and prereleases such as 0.8.0-rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it); the mcp extra's range is recorded.
- [ ] #3 Validate compatibility, licenses (including the mcp package and its tree in the extra), generated-file consistency and clean installation; the runtime still declares no dependencies.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The expected zero bridge delta is confirmed rather than assumed: no file under packages/qgis-sdk-typescript changed, no npm version is consumed, and the plugin-description contract version and HOST_FINGERPRINT still agree across both languages.
<!-- AC:END -->
