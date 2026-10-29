---
id: TASK-147
title: Keep the tail of MCP command output so failures stay diagnosable
status: To Do
assignee: []
created_date: '2026-10-29 13:36'
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
- [ ] #1 The one-shot path keeps the end of the stream (or a documented head+tail excerpt), so the traceback of an overflowing failing command survives; a test feeds more than the limit with a marker at the end and asserts the marker is in the report.
- [ ] #2 One documented truncation rule covers both one-shot and dev sessions, and guides/cli-mcp.md states what the caller loses when truncated is true.
- [ ] #3 Non-goals: no streaming/paging API and no change to the 256 KiB cap or the 300 s timeout.
<!-- AC:END -->
