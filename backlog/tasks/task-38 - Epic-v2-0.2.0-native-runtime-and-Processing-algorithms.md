---
id: TASK-38
title: 'Epic: v2 (0.2.0) native runtime and Processing algorithms'
status: To Do
assignee: []
created_date: '2026-10-24 14:14'
updated_date: '2026-10-24 16:12'
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
Tracking container for milestone m-1 (0.2.0), the first v2 increment after v0.1.1. It adds no scope of its own: the work is the five remaining m-1 feature tasks plus the 0.2.0 release gate (TASK-28), and the sprint train recorded in doc-9.

Why the container exists: the dependency graph already declares an order, but nothing on the board shows it. Two of the five feature tasks (TASK-14, TASK-3) are blocked on TASK-25, while TASK-5 and TASK-15 depend only on work that has landed. Reading m-1 as a flat list hides that TASK-25 is the only gateway on the critical path.

Sprint train (detail and rationale in doc-9):
1. Sprint 1 - TASK-25 curated native layer/project/notification/settings services and packaged QML. It is the only task that unblocks two others. Parallel, best-effort: TASK-15, which builds on the landed StepScheduler, or TASK-5, which needs only TASK-13 and TASK-24.
2. Sprint 2 - TASK-14 classified Processing algorithms with non-destructive outputs, plus TASK-3 schema-driven native UI, both consuming the TASK-25 contracts and both depending on TASK-25.
3. Sprint 3 - whatever remains of TASK-5 and TASK-15, then the TASK-28 release gate, which depends on all five.

Pairing: m-1 releases two artifacts at one shared version
([decision-24](../decisions/decision-24%20-%20Release-the-Python-SDK-and-TypeScript-bridge-at-one-shared-version.md)).
All five of this epic's features are Python-side, so 0.2.0 ships
`@archont561/qgis-sdk-bridge` with unchanged source; the m-1 "Bridge track"
section states that, and TASK-28 verifies the unchanged package instead of
skipping it. The typed bridge surface belongs to m-2 (TASK-4, TASK-17,
TASK-18, TASK-20).

Evidence rule for every increment: pure tests plus a real QGIS 4.2.3 host test where the task criteria require native behaviour. The Linux sandbox is headless, so no increment in this epic may claim Desktop GUI, canvas or WebEngine rendering evidence; those targets stay with TASK-33.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every remaining m-1 feature task (TASK-25, TASK-14, TASK-3, TASK-15, TASK-5) is closed with its own recorded evidence, including a real QGIS 4.2.3 host test wherever its criteria require native behaviour.
- [ ] #2 TASK-25 lands before TASK-14 and TASK-3 are started, so neither dependency-blocked feature is opened against services that do not exist yet.
- [ ] #3 The 0.2.0 release gate (TASK-28) is evaluated only after all five children are closed, and records actual artifacts, checks and explicit publishing approval — including the unchanged bridge artifact, built, packed and stamped at the shared version.
- [ ] #4 Unavailable targets stay explicit blockers rather than implied support: no Desktop GUI, Windows or macOS qualification is claimed from this epic (TASK-33 owns those).
<!-- AC:END -->
