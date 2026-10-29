---
id: TASK-147
title: Keep the tail of MCP command output so failures stay diagnosable
status: Done
assignee: []
created_date: '2026-10-29 13:36'
updated_date: '2026-10-29 13:51'
labels:
  - python
  - mcp
milestone: m-7
dependencies: []
priority: medium
type: bug
ordinal: 147000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
mcp.py caps each stream at 256 KiB with two different policies and no documented rule. _capture (one-shot commands) keeps the first 256 KiB and discards the rest, so when a verbose build or test run overflows, the traceback and the failing summary - the part a caller needs - are the bytes that get dropped; a probe with a 256 KiB head followed by a traceback returns truncated=true and no traceback. _DevSession._drain keeps the last 256 KiB instead. cli-mcp.md only says each stream is capped at 256 KiB, so neither policy is stated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The one-shot path keeps the end of the stream (or a documented head+tail excerpt), so the traceback of an overflowing failing command survives; a test feeds more than the limit with a marker at the end and asserts the marker is in the report.
- [x] #2 One documented truncation rule covers both one-shot and dev sessions, and guides/cli-mcp.md states what the caller loses when truncated is true.
- [x] #3 Non-goals: no streaming/paging API and no change to the 256 KiB cap or the 300 s timeout.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed: _keep_tail() is the single truncation rule; _capture (one-shot commands) and _DevSession._drain (dev sessions) both keep the most recent 256 KiB and set truncated. Test test_captured_output_keeps_the_tail_of_a_long_stream feeds 256 KiB of noise followed by a TRACEBACK marker and asserts the tail survives, the length equals _LIMIT, and the head is gone; it fails against the previous head-keeping _capture. guides/cli-mcp.md now states that the most recent 256 KiB is kept and that truncated means the beginning was dropped.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
One documented truncation rule keeps the diagnostic tail of every stream; a failing command's traceback no longer disappears behind its own verbosity.
<!-- SECTION:FINAL_SUMMARY:END -->
