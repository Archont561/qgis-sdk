---
id: TASK-78
title: Prepare and qualify 0.8.0 release
status: In Progress
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-29 23:20'
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
Explicit release gate for the plugin HTTP access release (m-7), not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization. Python side: runtime (explicit loopback HTTP API for plugin actions and streams), tools (mcp extra and plugin REST clients). The milestone expected the bridge unchanged; the gate measured 27 changed files instead, so the owner put the bridge minor (ts-v0.6.0) in the same train rather than leaving qualified sources unversioned - see AC 5 and doc-14.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required 0.8.0 work (TASK-74 and 75; TASK-76 was withdrawn with decision-49, so the plugin HTTP API is the client outside QGIS and the MCP list covers developer commands only) has verified outcomes and test/artifact evidence: Python suite with the mcp extra, tests/scripts, the devtools and build-install harnesses, the scripted MCP client over stdio plus the read-only derivation of the same list; doc-12 migration notes cover every added name and the security model.
- [x] #2 Use valid SemVer and prereleases such as 0.8.0-rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it); the mcp extra's range is recorded (mcp==2.3.0, and the kit's qgis-sdk-tools[mcp]==0.8.0 pin moves with the stamp).
- [x] #3 Validate compatibility, licenses (including the mcp package and its tree in the extra), generated-file consistency and clean installation; the runtime still declares no dependencies.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [x] #5 The bridge delta is confirmed rather than assumed: 27 files under packages/qgis-sdk-typescript changed (the bridge/store split, c278dec and 9397dee breaking), so the expectation of a zero delta was wrong and the owner put the bridge minor ts-v0.6.0 in this train; the wire is unchanged (HOST_FINGERPRINT sha256:16790dc8..., HOST_SCHEMA_VERSION 1, BRIDGE_PROTOCOL_VERSION 1) and the plugin-description contract version still agrees across both languages.
- [x] #6 Review TASK-140 FastAPI-style authoring spike for the requested 0.8.0 target; if implementation is approved for this release include its compatibility and migration and qualification evidence and revisit the expected unchanged bridge before release. (Reviewed: TASK-140 is Done, TASK-141 implemented the API and stays In Progress with its own AC 4 open for visible-GUI, other-platform and Conda qualification, which this release does not claim.)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-27: TASK-73 and TASK-77 re-scoped in from m-6; the gate's evidence covers the console session and the externals probe/vendoring too.

2026-10-29: gate run on main a362044, recorded in doc-14 '0.8.0 release gate (2026-10-29)'. AC 1, 3, 5 and 6 are evidenced there: the Python suite with the mcp extra (2173 passed / 56 skipped / 7 deselected, the three tests that skip without the extra included), tests/scripts 286, the static gate, the ten-task Bun suite and the coverage gate (95.70 % Python), the scaffold-web / reference / devtools / build-install / desktop-host harnesses, the 40-distribution clean install with the extra, licences across the whole mcp tree, the 7582-link docs build. AC 1's third task TASK-76 was withdrawn, and its 'both modes' is one served list plus the read-only derivation. AC 5 was rewritten: the measured delta is 27 files with two breaking commits, so the owner included ts-v0.6.0 in the train instead of recording the bridge as unchanged. AC 2 still waits for the stamp pull request (0.8.0 for the Python trio with the kit's mcp extra pin moving, ts 0.6.0, the ui components' peer range to >=0.6.0 <0.7.0, the scaffold pin, the migration-note headings); AC 4 waits for explicit publishing approval. Two tags are planned, python-v0.8.0 and ts-v0.6.0, on one merge commit.


2026-10-29 (after the gate): stamp rehearsal on the same tree, reverted afterwards. Both stamps move eight files; the kit's pins read 0.8.0 including tools[mcp], the tools' range >=0.8.0,<0.9 and the example's windows >=0.8,<0.9. verify-versions then fails only on the components' peer range and agrees on all five scopes once it moves to >=0.6.0 <0.7.0. The stamped wheels build and twine-check as 0.8.0, a fresh venv scaffolds >=0.8,<0.9 with bridge 0.6.0 and checks clean, a 0.7-scaffolded project under those tools reports exactly VERSION001 and VERSION004, and the stamped purity lane fails six tests that are all the one SDK_NPM_VERSION literal in test_scaffold_web.py. That literal, the peer range and the two migration-note headings are the stamp PR's code change. The rc.1 pair (python-v0.8.0-rc.1, ts-v0.6.0-rc.1 on the stamp merge commit) and what each run must show are written down in doc-14 under '0.8.0 rehearsal and tag plan'; AC 2 still waits for the actual stamp, AC 4 for the release instruction.


2026-10-29 (stamp pull request, on 951ec3f): owner said "release". stamp --scope python 0.8.0 moved the three manifests, the kit's three exact pins (tools[mcp] included), the tools' range >=0.8.0,<0.9, the recipe's three versions and the example's windows; stamp --scope typescript 0.6.0 moved package.json, the alias and SDK_NPM_VERSION. By hand: the ui peer range >=0.6.0 <0.7.0 in the scoped package and its alias, the one SDK_NPM_VERSION literal in test_scaffold_web.py, the doc-12/doc-13 migration headings, and the README status lines. verify-versions agrees on 0.8.0 / 0.6.0 / 0.1.0 and contract v1. Stamped-tree evidence in doc-14 under 'Stamp and artifacts' and 'On the stamped tree': 10/10 Bun tasks, Python 2173/56, coverage 95.70 %, purity 1995/22, all six harnesses, docs 8096 links 0 broken, three 0.8.0 wheels with twine checks, four npm tarballs, a clean 12-distribution install whose [mcp] extra resolves with no warning for the first time, and a 0.7.0-scaffolded project reporting exactly VERSION001 and VERSION004. One finding: the alias mirror test is what catches the ui peer range, because the alias is not a stamp target - both files must move. AC 2 is done; AC 4 stays open until the tags run.

<!-- SECTION:NOTES:END -->
