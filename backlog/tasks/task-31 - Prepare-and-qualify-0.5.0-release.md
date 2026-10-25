---
id: TASK-31
title: Prepare and qualify 0.5.0 release
status: Done
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-25 21:09'
labels: []
milestone: m-4
dependencies:
  - TASK-9
  - TASK-22
  - TASK-30
references:
  - doc-8
priority: high
type: chore
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required 0.5.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [x] #2 Use valid SemVer and prereleases such as 0.5.0-alpha.1; update actual manifests only for released packages and document migration notes.
- [x] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [x] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [x] #5 The bridge is qualified as a pair, not as a bystander: the record states which bridge version ran inside a real `QWebEngineView` against which `qgis-sdk` version, any defect the matrix finds lands as a recorded bridge source change with its own changelog entry, and no bridge version is published unless such a fix exists.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate run 2026-10-25 on main 3c7aaa5 + this branch; the full record is doc-14 '0.5.0 release gate (TASK-31)'. Publishing approval: the owner chose 'Gate + stamp + tag + publish' (2026-10-25) when offered gate-only / gate+stamp / full, with a pause for 'Merge' on each PR; tag python-v0.5.0 goes on the merge commit of the gate-and-stamp PR. Bridge pair (AC 5): @archont561/qgis-sdk 0.3.0 inside a real QWebEngineView against the 0.5.0 runtime, contract version 1 both sides, no defect, no bridge publish. ACs are checked only after the tag's release.yml run is green and the artifacts are verified.

Released 2026-10-25: PR #83 (gate record + stamp) merged as 386089b; annotated tag python-v0.5.0 on it; release.yml run 40232586520 green (build, conda, pypi, github-release; npm/github-packages skipped). PyPI serves qgis-sdk, qgis-sdk-runtime and qgis-sdk-tools 0.5.0 with the same sha256 as the wheels built in the gate (d4d933d9…, c5f3a3ac…, 7c2247ca…); pip install qgis-sdk==0.5.0 from the index resolves cleanly on CPython 3.11.2; GitHub Release carries three wheels, three Conda packages and SHA256SUMS; prefix.dev uploads succeeded per the job log. AC 1: required work (TASK-57, TASK-22, TASK-9) Done with evidence in doc-14; open targets (TASK-33 Windows/macOS QGIS, display-server GUI, decision-15, decision-19) recorded as blockers, not smoothed over. AC 2: 0.5.0 after the 0.5.0-rc.1 rehearsal, Python manifests only, migration note in doc-12. AC 3: compatibility (verify-versions, VERSION001/002, tools range >=0.5.0,<0.6), licences (MIT LICENSE in each wheel, NOTICE in the ZIP), generated files (--check up to date), clean install on 3.11.2 and 3.14.8; contract versions stay 1 and independent of package versions. AC 4: artifacts, checks and the explicit approval are in doc-14 '0.5.0 release gate'; no 1.0 promise, nothing automatic, nothing claimed unrun (the Conda build ran only in the tag's workflow). AC 5: @archont561/qgis-sdk 0.3.0 inside a real QWebEngineView against the 0.5.0 runtime, contract 1 both sides, no defect, no bridge publish.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 19:10
---
AC #5 was added on 2026-10-24 to carry the bridge obligation [m-4](../milestones/m-4%20-%200.5.0-%E2%80%94-qualified-experimental-reference-release.md) already states: this milestone qualifies the bridge instead of extending it, TASK-9's compatibility gate has to name the pair, TASK-22 is the first evidence the transport works in a real view, and a defect found here is a bridge source change that does not hide inside "qualification fixes". The earlier criteria said "update actual manifests only for released packages", which is true but silent about who qualifies the bridge and how a defect is published. No criterion had been checked.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->
