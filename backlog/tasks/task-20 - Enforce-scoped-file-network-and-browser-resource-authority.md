---
id: TASK-20
title: Enforce scoped file network and browser resource authority
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-2
dependencies:
  - TASK-24
  - TASK-23
  - TASK-5
references:
  - >-
    backlog/decisions/decision-20 -
    Enforce-scoped-host-authority-and-stale-reference-failures.md
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: medium
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enforce scoped file network and browser resource authority. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Trusted host view/origin/generation binding rejects forged callers; scoped handles fail when stale/foreign.
- [ ] #2 Picker/plugin file grants constrain effects and exports; host network grants restrict origins/methods/auth/redirects.
- [ ] #3 Real WebEngine navigation/resource tests prevent bypass; define revocation and borrowed-resource release without deleting user layers.
<!-- AC:END -->
