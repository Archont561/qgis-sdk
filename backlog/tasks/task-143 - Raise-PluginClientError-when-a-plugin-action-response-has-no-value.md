---
id: TASK-143
title: Raise PluginClientError when a plugin action response has no value
status: Done
assignee: []
created_date: '2026-10-29 13:35'
updated_date: '2026-10-29 13:51'
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
- [x] #1 Against a stub server replying 200 {"ok": true}, PluginClient.call raises PluginClientError rather than KeyError, and the message names the missing value.
- [x] #2 A test attaches the stub to the public PluginClient.call seam; the existing happy-path and CLI tests still pass.
- [x] #3 Non-goals: no new client-layer abstraction and no change to a successful call's return value.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed in PluginClient.call: the reply is read into a local and a missing value now raises PluginClientError('Plugin response has no value') instead of a bare KeyError. Seam: test_a_response_without_a_value_is_a_client_error in test_plugin_rest.py drives a throwaway loopback stub that answers 200 {"ok": true}; it fails against the previous code (KeyError) and passes now.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A plugin reply without a value is a documented PluginClientError carrying the reason; no new abstraction and the success path is unchanged.
<!-- SECTION:FINAL_SUMMARY:END -->
