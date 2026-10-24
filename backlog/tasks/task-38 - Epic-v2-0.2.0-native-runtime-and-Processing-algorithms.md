---
id: TASK-38
title: 'Epic: v2 (0.2.0) native runtime and Processing algorithms'
status: To Do
assignee: []
created_date: '2026-10-24 14:14'
updated_date: '2026-10-24 16:54'
labels: []
milestone: m-1
dependencies:
  - TASK-25
  - TASK-14
  - TASK-3
  - TASK-15
  - TASK-5
references:
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
  - backlog/docs/plans/doc-4 - SemVer-delivery-roadmap-and-task-dependencies.md
  - backlog/milestones/m-1 - 0.2.0-—-native-runtime-and-processing-algorithms.md
  - >-
    backlog/docs/doc-10 -
    Backlog-conventions-vocabulary-statuses-and-predicates.md
priority: high
type: feature
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tracking container for milestone m-1 (0.2.0), the first v2 increment after v0.1.1. It adds no scope of its own: the work is the remaining m-1 feature tasks plus the 0.2.0 release gate (TASK-28), and the sprint train recorded in doc-9.

Why the container exists: the dependency graph already declares an order, but nothing on the board shows it. TASK-14 and TASK-3 were both blocked on TASK-25, which was the only gateway on the critical path; reading m-1 as a flat list hid that.

Sprint train (detail and rationale in doc-9):
1. Sprint 1 - TASK-25 curated native layer/project/notification/settings services and packaged QML. Done: TASK-25 and its five slices closed 2026-10-24 with doc-11 as evidence.
2. Sprint 2 - TASK-14 classified Processing algorithms with non-destructive outputs, plus TASK-3 schema-driven native UI, both consuming the TASK-25 contracts. TASK-14 is Done; TASK-3 is the remaining feature.
3. Sprint 3 - the TASK-28 release gate.

Re-scoped on 2026-10-24: TASK-5 (QGIS-aware HTTP client) and TASK-15 (scoped local jobs) moved to m-2. They blocked nothing here, they are not part of the "native runtime and Processing" surface this milestone is named for, and both still depend on design decisions that are only proposed (decision-4 for the networking transport, decision-13 for job transport). Leaving them in m-1 delayed a release that is otherwise ready. The rationale is recorded in m-1 and in doc-9 section 4a.

Pairing: 0.2.0 releases the Python package only. The bridge has no source
change in m-1, so it is not published and stays at 0.1.1
([decision-25](../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md));
what the release still proves is that the plugin-description contract version
agrees across both languages. The typed bridge surface belongs to m-2 (TASK-4,
TASK-17, TASK-18, TASK-20), and that milestone releases the bridge at its own
0.2.0.

Evidence rule for every increment: pure tests plus a real QGIS 4.2.3 host test where the task criteria require native behaviour. The Linux sandbox is headless, so no increment in this epic may claim Desktop GUI, canvas or WebEngine rendering evidence; those targets stay with TASK-33.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every m-1 feature task is closed with its own recorded evidence, including a real QGIS 4.2.3 host test wherever its criteria require native behaviour: TASK-25 (and its slices), TASK-14, TASK-39 and TASK-3. TASK-5 and TASK-15 left the milestone on 2026-10-24 and are m-2's.
- [ ] #2 TASK-25 landed before TASK-14 and TASK-3 were opened, so neither dependency-blocked feature was started against services that did not exist yet. Satisfied: TASK-25 closed 2026-10-24 before TASK-14 landed, and TASK-3 was never opened early.
- [ ] #3 The 0.2.0 release gate (TASK-28) is evaluated only after its children are closed, and records actual artifacts, checks and explicit publishing approval - including the contract version agreeing across both languages, with no bridge version published.
- [ ] #4 Unavailable targets stay explicit blockers rather than implied support: no Desktop GUI, Windows or macOS qualification is claimed from this epic (TASK-33 owns those).
<!-- AC:END -->
