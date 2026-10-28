---
id: TASK-127
title: Evaluate class-level surface open convenience
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: low
type: spike
ordinal: 127000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner asked about BufferDialog.open(). Today a plugin action uses self.ctx.ui.open(BufferDialog, initial=...) and class-level toolbar/menu/shortcut bindings can open a registered surface. A global class method has no unambiguous plugin/view owner when multiple runtimes use the class; no convenience API is implemented.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide whether a safe instance- or context-bound convenience is worthwhile and whether any class syntax can be unambiguous without a global current-plugin singleton.
- [ ] #2 Document and test view/plugin ownership, surface registration, initial values, dialog versus dock lifecycle, two concurrent plugin runtimes, close/reload and host capability refusal.
<!-- AC:END -->
