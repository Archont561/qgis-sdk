---
id: TASK-143
title: Raise PluginClientError when a plugin action response has no value
status: To Do
assignee: []
created_date: '2026-10-29 13:35'
labels:
  - python
  - http
milestone: m-7
dependencies: []
priority: medium
type: bug
ordinal: 143000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PluginClient.call returns self._json(...)["value"]. A 200 response whose JSON object lacks "value" - a different server version, a proxy, or a future error shape - raises KeyError instead of the PluginClientError the class documents, so a caller that catches the documented failure type crashes with a traceback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Against a stub server replying 200 {"ok": true}, PluginClient.call raises PluginClientError rather than KeyError, and the message names the missing value.
- [ ] #2 A test attaches the stub to the public PluginClient.call seam; the existing happy-path and CLI tests still pass.
- [ ] #3 Non-goals: no new client-layer abstraction and no change to a successful call's return value.
<!-- AC:END -->
