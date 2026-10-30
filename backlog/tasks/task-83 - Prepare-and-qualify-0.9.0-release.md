---
id: TASK-83
title: Prepare and qualify 0.9.0 release
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-30 17:12'
labels: []
milestone: m-8
dependencies:
  - TASK-78
  - TASK-80
  - TASK-81
  - TASK-82
  - TASK-115
  - TASK-116
  - TASK-117
type: chore
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the 0.9.0 hosts and worker-first named jobs release (m-8, decisions 52 and 65, amending decision-53), not evidence of release or permission to publish. Python-only release; the bridge is expected unchanged and that is confirmed, not assumed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name, including worker-first jobs, restricted context, named registration, action handles and legacy async/offload migration.
- [ ] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The expected zero bridge delta is confirmed rather than assumed: no file under packages/qgis-sdk-typescript changed, no npm version is consumed, and HOST_FINGERPRINT and the plugin-description contract version still agree across both languages. A changed wire requires a separate contract/version decision and revised gate.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate must record the server-bindings row (decision-52 implementation note, 2026-10-30): the in-process QgsServer test of TASK-80 #2 needs a QGIS built with WITH_SERVER=ON plus bindings, which no conda build has (conda-forge passes -D WITH_SERVER=FALSE) and which the workspace pixi environment therefore lacks. State whether the row ran (CI job installing qgis-server plus python3-qgis, or a machine where `from qgis.server import QgsServer` imports) or was blocked, with the evidence, and never count it as passed on the strength of the fake-interface tests.
The server row exists now (2026-10-30): `.github/workflows/ci.yml` gained the `Server host` job (qgis.org `qgis-server` + `python3-qgis` on `ubuntu-24.04`, `scripts/ci.py server`, wired into the `checks` aggregate) and the suite gained the `server` test layer. The gate reads that job's result for TASK-80 AC 2 and records it as run or blocked with the log, never as an assumption; the row's first green run is what moves #2 from "the environment is right" to "the same plugin class serves a request inside a QgsServer".
The `Server host` row has run green once (2026-10-30, run 41109578499): qgis.org `qgis-server` + `python3-qgis` on `ubuntu-24.04`, QGIS 3.44.7 with `qgis.server` present, the `server` layer executed rather than skipped, and the `checks` aggregate gated on it. The gate records that run for TASK-80 AC 2 with the version caveat the task note carries - the repository ships the 3.44 LTS line today, so the row is evidence for the bindings and the dispatcher, not yet a 4.x server claim.
<!-- SECTION:NOTES:END -->
