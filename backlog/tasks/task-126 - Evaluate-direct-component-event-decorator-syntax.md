---
id: TASK-126
title: Evaluate direct component event decorator syntax
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: low
type: spike
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner asked whether @ping.clicked could replace @on(ping).clicked. Today Button.clicked(listener) subscribes immediately and returns an unsubscribe callback, so simply using it as a decorator would replace the handler incorrectly. No new syntax was approved or implemented.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Evaluate an unambiguous declaration syntax that preserves existing clicked(listener) and unsubscribe semantics and the supported @on(ping).clicked form.
- [ ] #2 Prove instance-scoped per-surface wiring, multiple views, no registration at class-definition time, handler identity, automatic disposal and no reload leaks; explain static typing and collision behavior.
<!-- AC:END -->
