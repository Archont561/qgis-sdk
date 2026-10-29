---
id: TASK-78
title: Prepare and qualify 0.8.0 release
status: To Do
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-28 17:39'
labels: []
milestone: m-7
dependencies:
  - TASK-32
  - TASK-74
  - TASK-75
  - TASK-79
  - TASK-73
  - TASK-77
  - TASK-140
type: chore
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the plugin HTTP access release (m-7), not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization. Python-only release: runtime (explicit loopback HTTP API for plugin actions and streams), tools (mcp extra and plugin REST clients); the bridge is expected unchanged and that expectation is confirmed, not assumed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.8.0 work (TASK-74, 75, 76) has verified outcomes and test/artifact evidence: Python suite with the mcp extra, tests/scripts, the devtools and build-install harnesses, the scripted MCP client against both modes; doc-12 migration notes cover every added name and the security model.
- [ ] #2 Use valid SemVer and prereleases such as 0.8.0-rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it); the mcp extra's range is recorded.
- [ ] #3 Validate compatibility, licenses (including the mcp package and its tree in the extra), generated-file consistency and clean installation; the runtime still declares no dependencies.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The expected zero bridge delta is confirmed rather than assumed: no file under packages/qgis-sdk-typescript changed, no npm version is consumed, and the plugin-description contract version and HOST_FINGERPRINT still agree across both languages.
- [ ] #6 Review TASK-140 FastAPI-style authoring spike for the requested 0.8.0 target; if implementation is approved for this release include its compatibility and migration and qualification evidence and revisit the expected unchanged bridge before release.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-27: TASK-73 and TASK-77 re-scoped in from m-6; the gate's evidence covers the console session and the externals probe/vendoring too.
<!-- SECTION:NOTES:END -->
