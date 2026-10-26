---
id: TASK-74
title: >-
  Add the loopback agent transport to the runtime with per-session authority and
  the AGENT check rules
status: To Do
assignee: []
created_date: '2026-10-26T09:48:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-64
  - TASK-66
type: enhancement
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-49 points 1 and 6. qgis_sdk.agent: a stdlib http.server thread bound to 127.0.0.1 only, bearer token from a 0600 file, Origin checked; one ViewBinding per session; every request handed to the GUI thread through the scheduler and dispatched through ChannelTransport; stream frames as server-sent events; disconnect disposes the binding; plugin reload invalidates the generation. Grants from [tool.qgis-sdk.agent] (actions, grants, per-action read_only/destructive annotations) through register_host_operations(only=) and an action allowlist; nothing exposed without them. check gains AGENT001 (exposed action without annotation), AGENT002 (unknown grant), AGENT003 (enabled without exposed actions). No eval, no non-loopback bind, no new dependency.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The bridge test vectors pass over the loopback transport unchanged; a wrong or missing token, a foreign Origin or a non-loopback bind attempt is refused (pure tests with a scripted HTTP client, no Qt); every dispatch runs on the GUI thread and a stream delivers ordered SSE frames (qgis native tests).
- [ ] #2 An action or host operation outside the agent allowlist is refused by the dispatcher with the structured code, a plugin reload fails in-flight calls with the host-reloaded error, and a session's handles and subscriptions die with its disconnect (pure + native tests).
- [ ] #3 check reports AGENT001-003 with remediations on fixture projects; HOST_FINGERPRINT, HOST_SCHEMA_VERSION and BRIDGE_PROTOCOL_VERSION are unchanged and shown so; the runtime manifest still declares no dependencies.
<!-- AC:END -->
