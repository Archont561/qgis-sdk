---
id: TASK-144
title: Answer a plugin HTTP capacity refusal with 503 instead of 400
status: Done
assignee: []
created_date: '2026-10-29 13:35'
updated_date: '2026-10-29 13:51'
labels:
  - python
  - http
milestone: m-7
dependencies: []
priority: low
type: bug
ordinal: 144000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PluginHttpServer._error_status maps only host_busy to 503; every other error code becomes 400. The per-plugin session cap therefore reports "capacity / Too many sessions" as a client error, so a client cannot tell a retryable server condition from a malformed request. The documented behaviour reserves 503 for overload.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A capacity refusal answers 503 with its structured error body, and the error-status mapping has one table that the tests assert for each code the server can return (host_busy, capacity, invalid_request, operation_failed).
- [x] #2 A test reaches the refusal through HTTP - a server configured so the stream cap can be reached - and asserts both the status and the code; the client surfaces the status in its message.
- [x] #3 Non-goals: no retry or backoff logic in PluginClient and no change to the 200 shape.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Audit note (2026-10-29): the session cap can only be reached when PluginHttpServer is configured with max_event_streams >= 64 (the default is min(16, max_connections - 1)), because each event-stream slot bounds one session and its release disposes that session. Configure the server accordingly (e.g. max_connections=130, max_event_streams=128) to reach it over HTTP; if holding 64 concurrent SSE streams proves too slow for the suite, pin the mapping table per code and keep the existing real 503 test (test_sse_capacity_reserves_a_connection_for_calls) as the HTTP-level evidence.

Fixed: _server.py now owns one table, _ERROR_STATUS = {host_busy: 503, host_reloaded: 503, capacity: 503}, and _error_status falls back to 400 for anything else; the duplicated session guard became PluginHttpServer._capacity_error(). Tests: test_error_codes_map_to_one_status_table pins every code, and test_the_session_budget_answers_503_with_its_code holds 64 streams on a server configured max_connections=130 / max_event_streams=128 and asserts the 65th answers 503 with code capacity. Both fail against the previous mapping (400). The carried note about reaching the cap through configuration is satisfied; no mapping-table fallback was needed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Retryable overload, including the session budget, answers 503 from one status table; malformed input and failed operations stay 400.
<!-- SECTION:FINAL_SUMMARY:END -->
