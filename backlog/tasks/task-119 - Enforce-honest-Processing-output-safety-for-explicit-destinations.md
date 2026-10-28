---
id: TASK-119
title: Enforce honest Processing output safety for explicit destinations
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
NativeAlgorithms.run passes explicit destinations to Processing and cleans only the SDK-owned run directory on failure. A sandbox probe using a simulated failing Processing backend confirmed an externally written partial file remains. There is no input/output alias check; arbitrary registered providers may have other side effects. Existing no-partial-output and never-edit-input documentation overclaims these guarantees. No input corruption was demonstrated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Design and implement safe handling for explicit and allocated destinations, including input aliases and existing user files; never delete or replace user data blindly. Fail closed where the promised guarantee cannot be provided.
- [ ] #2 Test failed runs and successful runs with external, existing, aliased and SDK-allocated destinations, plus native provider cases; distinguish fake-backend evidence from real QGIS provider guarantees.
- [ ] #3 Document precise cleanup, atomicity and trusted third-party algorithm limitations and reconcile Algorithms protocol and guide promises; preserve declared contract compatibility or document a breaking migration.
<!-- AC:END -->
