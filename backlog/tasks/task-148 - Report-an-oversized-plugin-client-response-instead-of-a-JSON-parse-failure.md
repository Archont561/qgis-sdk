---
id: TASK-148
title: Report an oversized plugin client response instead of a JSON parse failure
status: Done
assignee: []
created_date: '2026-10-29 13:37'
updated_date: '2026-10-29 13:51'
labels:
  - python
  - http
milestone: m-7
dependencies: []
priority: low
type: bug
ordinal: 148000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PluginClient._json reads at most 1 MiB of the body (response.read(1024 * 1024)) and then parses it. A well-formed 200 response larger than 1 MiB - a describe() on a large plugin, or a call() returning a big result - is silently cut mid-token and surfaces as "Unterminated string starting at: line 1 column 11", which points at the JSON text rather than at the size limit. A probe against a stub server returning 2 MiB reproduces it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A response that exceeds the client's read bound raises PluginClientError saying the response was too large, with the bound in the message; a test attaches a stub server with an oversized body to PluginClient.call.
- [x] #2 A response exactly at the bound still parses, and the bound is a single named constant shared by the JSON and stream paths.
- [x] #3 Non-goals: do not add a paging or streaming download API, and do not change the server's 1 MiB response expectations.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed: rest.py has one _RESPONSE_LIMIT (1 MiB) shared by the JSON body read, the error body and the SSE frame bound. A body longer than the limit raises PluginClientError('Plugin response exceeds 1048576 bytes'); frames report the same bound. Tests: test_an_oversized_response_names_the_bound (2 MiB body, fails against the old truncated-parse 'Unterminated string' message) and test_a_response_exactly_at_the_bound_still_parses (a body of exactly 1048576 bytes still returns its value).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
An oversized reply is reported as too large with the bound in the message, from a single constant shared by the JSON and stream paths.
<!-- SECTION:FINAL_SUMMARY:END -->
