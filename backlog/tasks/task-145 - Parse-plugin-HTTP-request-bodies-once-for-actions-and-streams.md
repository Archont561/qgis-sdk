---
id: TASK-145
title: Parse plugin HTTP request bodies once for actions and streams
status: To Do
assignee: []
created_date: '2026-10-29 13:36'
updated_date: '2026-10-29 13:36'
labels:
  - python
  - refactor
milestone: m-7
dependencies: []
priority: medium
type: task
ordinal: 145000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Content-Length validation, 413 size limit, JSON parse, short-read check and object check in _server.py are duplicated verbatim in _rest_action and _rest_stream (about 21 lines each; only the action/stream lookup line differs), and the 64-session capacity guard is copied in both too. These are security-relevant request rules with two copies, and they already drifted once while this surface was being written. Behaviour-preserving refactor.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One private helper performs the body read and JSON-object validation for both handlers, and the duplication between _rest_action and _rest_stream is gone; the capacity guard has one implementation.
- [ ] #2 The behaviour does not change: the existing limits tests (413 oversized, 400 ambiguous Content-Length and non-object payload, truncated body never dispatched, capacity) pass unchanged, and no new test is needed to prove it.
- [ ] #3 Non-goals: do not restructure the handler class or split _server.py; this is the smallest extraction that removes the copies.
<!-- AC:END -->
