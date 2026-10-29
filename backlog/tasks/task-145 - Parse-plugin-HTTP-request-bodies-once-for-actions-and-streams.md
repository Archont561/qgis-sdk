---
id: TASK-145
title: Parse plugin HTTP request bodies once for actions and streams
status: Done
assignee: []
created_date: '2026-10-29 13:36'
updated_date: '2026-10-29 13:51'
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
- [x] #1 One private helper performs the body read and JSON-object validation for both handlers, and the duplication between _rest_action and _rest_stream is gone; the capacity guard has one implementation.
- [x] #2 The behaviour does not change: the existing limits tests (413 oversized, 400 ambiguous Content-Length and non-object payload, truncated body never dispatched, capacity) pass unchanged, and no new test is needed to prove it.
- [x] #3 Non-goals: do not restructure the handler class or split _server.py; this is the smallest extraction that removes the copies.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed: Handler._json_object_body() is now the single reader for POST /actions and POST /streams (same Content-Length checks, _MAX_BODY_BYTES 413, JSON parse, short-read and object checks); the 64-session guard is PluginHttpServer._capacity_error() with _MAX_SESSIONS. No behaviour change: the 16 tests in test_plugin_http_limits.py (413 oversized, ambiguous Content-Length, non-object payload, truncated body never dispatched, capacity, deadlines) pass unchanged, as do the 16 in test_plugin_rest.py.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The security-relevant request rules and the session budget have one implementation each; the diff removes 42 duplicated lines without changing an observable behaviour.
<!-- SECTION:FINAL_SUMMARY:END -->
