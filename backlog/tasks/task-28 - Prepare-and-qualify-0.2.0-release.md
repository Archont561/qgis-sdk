---
id: TASK-28
title: Prepare and qualify 0.2.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 16:54'
labels: []
milestone: m-1
dependencies:
  - TASK-1
  - TASK-3
  - TASK-14
  - TASK-24
  - TASK-25
  - TASK-27
references:
  - doc-8
priority: high
type: chore
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.2.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.2.0-alpha.1; stamp the Python manifests only (`pyproject.toml`, `recipe.yaml`) at an explicitly advanced minor, leave the bridge `package.json` at its own 0.1.1 and publish no bridge version, and document migration notes (including the required `AlgorithmContext.algorithms`).
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---

author: qgis-sdk agent
created: 2026-10-24 16:05
---
AC #2 amended on 2026-10-24, before any of this task's criteria was checked: it said 'update actual manifests only for released packages', which encoded the old policy that the two packages are versioned independently. decision-24 replaced that policy, so the criterion now says the one shared version is stamped into both released manifests and the minor is advanced explicitly at this milestone close. Consequence worth planning for: release.py plan no longer proposes a minor bump for feature work - on this branch it proposes v0.1.2 - so the 0.2.0 release must pass --bump minor or --version-override 0.2.0 rather than accepting the derived answer. The invariant is enforced by release.py verify-versions (also wired into the build job of release.yml).
---

author: qgis-sdk agent
created: 2026-10-24 16:25
---
AC #2 amended again on 2026-10-24, still before any criterion was checked: decision-25 replaced decision-24 while this task was open. The Python manifests are stamped on their own and the bridge is deliberately left at 0.1.1 and not published. Practical consequences for this gate: plan with 'release.py plan --scope python --bump minor' (a plain plan proposes python-v0.1.2), stamp with 'stamp --scope python --version 0.2.0', and verify with 'verify-versions --scope python --version 0.2.0', which also refuses a plugin-description contract version that disagreed across the two languages. No ts-v* tag is created; the bridge's next release is m-2's.
---

author: qgis-sdk agent
created: 2026-10-24 16:54
---
Dependencies updated on 2026-10-24: TASK-5 and TASK-15 moved to m-2 under the 0.2.0 re-scope and were removed from this gate. Among feature work the gate now waits on TASK-3 alone (TASK-1, TASK-14, TASK-24, TASK-25 and TASK-27 are Done; TASK-39 landed as part of the Processing half). AC #2 is unchanged: the Python manifests are stamped at an explicitly advanced minor, the bridge stays at 0.1.1 and is not published.
---
<!-- COMMENTS:END -->
