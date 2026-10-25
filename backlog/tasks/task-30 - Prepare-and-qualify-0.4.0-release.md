---
id: TASK-30
title: Prepare and qualify 0.4.0 release
status: Done
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T17:13:00Z'
labels: []
milestone: m-3
dependencies:
  - TASK-6
  - TASK-8
  - TASK-16
  - TASK-19
  - TASK-21
  - TASK-26
  - TASK-29
references:
  - doc-8
priority: high
type: chore
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required 0.4.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [x] #2 Use valid SemVer and prereleases such as 0.4.0-alpha.1; release Python at its own explicitly advanced minor and release the bridge only if it changed, at a patch of its own version; verify both scopes plus the shared contract version, and document migration notes.
- [x] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [x] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [x] #5 The milestone's "no bridge source change" claim is tested rather than assumed: the release diff touches no file under `packages/qgis-sdk-typescript`, or every such change is recorded with its own changelog entry and a bridge patch released at its own version.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Qualification run 2026-10-25 on main 7c7a1d0 (Linux, QGIS 4.2.3, Bun 1.4.2); full record in doc-14 '0.4.0 release gate' and the doc-16 close line. AC1: TASK-6/8/16/19/21/26/29 Done; merges #65, #69-#71, #73, #74, CI green on all three jobs. AC2: release.py plan --scope python --bump minor from python-v0.3.0 -> python-v0.4.0 (10 feat, 3 fix); push default would be 0.3.1, so the minor is the explicit act; plan --scope typescript skips (nothing since ts-v0.3.0); verify-versions: both scopes 0.3.0, contract 1; migration notes are doc-12 'Unreleased migration notes' (heading renamed at stamp). Fixed on the way: the generated changelog dropped PR #65's four features because release.py only knew the post-rename package prefix (test added). AC3: lint/format/release-tool/actionlint/typecheck/biome/bridge --check clean; Bun 3/3, coverage 96.19%, Python 1369 passed/38 skipped, tests/scripts 192; opt-in harnesses one file per process: 5/22/23/10/8/6+1s/112/9/1/9 all passed; build-python + verify-python (twine) pass; wheel has LICENSE, no tests, console script, typer only; clean venv: imports without qgis, new/check/build end to end, unpacked ZIP imports with the SDK absent. Licences: wheel MIT LICENSE, ZIP SDK NOTICE - that is all build validates because DEP001 refuses third-party code. AC5: git diff ts-v0.3.0..main under packages/qgis-sdk-typescript and packages/qgis-sdk-alias is empty; no bridge release. Also: decision-15 accepted (presentation-state restore deferred), doc-4 bridge cell corrected to 0.3.0, conftest skips the other webengine modules when the scaffold-web harness shares the process (was exit 134). AC4 open: no stamp, tag, release or upload has been made; waiting for the explicit request.

2026-10-25 (stamped, not yet tagged): stamp requested in the session ('do stamp PR'). 'release.py stamp --scope python --version 0.4.0' wrote pyproject.toml and recipe.yaml; the bridge stays 0.3.0 (no change since ts-v0.3.0). verify-versions: python 0.4.0, typescript 0.3.0, contract 1. plan --scope python --bump minor plans python-v0.4.0. build-python + verify-python pass on qgis_sdk-0.4.0-py3-none-any.whl (sha256 66de7e45...3a7eb7); in a clean venv the wheel reports 0.4.0 and 'new/check/build' vendors runtime 0.4.0. doc-12 'Unreleased migration notes' became '0.4.0 migration notes' with the release intro and the manifests bullet. Python suite 1369 passed/38 skipped, tests/scripts 192, ruff clean. Still open for AC4: tag python-v0.4.0 on the main merge commit after this PR lands, release.yml builds wheel + conda and publishes; record the result here.

2026-10-25 (released): tag python-v0.4.0 created on main a6b3d8e (merge of stamp PR #76) on the explicit request 'create tag and push it'. release.yml run 40214978629: build, conda, pypi, github-release success; npm and github-packages skipped (Python scope). PyPI qgis-sdk 0.4.0 is live (wheel sha256 66de7e45...3a7eb7, identical to the wheel built locally before the stamp); prefix.dev conda qgis-sdk-0.4.0-pyh4616a5c_0.conda (sha256 6354bbdc...2128a) attested by the job log (prefix.dev not reachable from the sandbox); GitHub Release python-v0.4.0 carries wheel, conda and SHA256SUMS, notes edited to the 0.4.0 summary and the feature/fix list. No bridge tag: ts-v0.3.0 stays current. AC4 closed; the milestone's Python artifact is delivered.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 19:10
---
AC #5 was added on 2026-10-24 to carry the bridge obligation [m-3](../milestones/m-3%20-%200.4.0-%E2%80%94-developer-workflow-and-plugin-packaging.md) already states: 0.4.0 adds consumers of the published bridge, not surface, and the milestone says outright that this is a claim the release gate tests rather than assumes. No criterion had been checked, so nothing was invalidated. The bridge versions independently ([decision-25](../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)), so a consumer-driven fix is a patch of the bridge's own number, never a renumbering to match Python.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->
