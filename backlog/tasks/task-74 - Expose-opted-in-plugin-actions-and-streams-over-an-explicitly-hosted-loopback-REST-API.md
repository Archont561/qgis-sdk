---
id: TASK-74
title: >-
  Expose opted-in plugin actions and streams over an explicitly hosted loopback
  REST API for clients outside QGIS
status: In Progress
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-29 12:00'
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
Replace the earlier runtime "agent" transport with a plain REST interface. The host, not project metadata, explicitly starts a stdlib `http.server` listener on 127.0.0.1 with a bearer token from a 0600 file; browser Origins and foreign Host headers are refused. `GET /plugin` returns the filtered plugin description, `POST /actions/<id>` calls an allowlisted action and `POST /streams/<id>` serves server-sent events. Every request is handed to the QGIS owner thread through the existing scheduler and dispatched through `ChannelTransport`; bindings are disposed on disconnect and close.

The boundary is deliberate: MCP in `qgis-sdk-tools` serves developers and agents at the project level, while this HTTP API is the only runtime interface for calling an opted-in plugin from outside QGIS. Plugin access is not exposed through MCP. `qgis-sdk plugin describe|call|stream` and `qgis_sdk_tools.rest.PluginClient` provide the external clients. There is no runtime agent module, no automatic metadata activation and no host-operation grants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The host explicitly starts and closes the server; construction neither listens nor creates a token, the token is private and removed on close, non-loopback binds, foreign Host headers, browser Origins, wrong tokens and unknown action or stream IDs are refused, and only one endpoint may serve a runtime (pure tests).
- [ ] #2 An allowlisted action dispatches on the QGIS owner thread; a queued call past its deadline fails with the documented busy error and is withdrawn before it can run, and a reload fails in-flight calls with the host-reloaded error without running withdrawn work (pure and native tests).
- [ ] #3 Streams deliver ordered SSE frames, honour the event-stream capacity limit, bound frame size and buffered bytes, and dispose their subscription on client disconnect or server close (pure and native tests).
- [x] #4 The Python client and CLI call a live plugin and stream events without importing the runtime; the CLI MCP inventory contains no plugin REST commands (tests at the public seams).
- [ ] #5 Real QGIS qualification covers owner-thread dispatch and teardown/reload, the built plugin vendors `qgis_sdk.http` only on explicit import, and no `qgis_sdk.agent` module, agent checker, guide or test remains.
<!-- AC:END -->

## Implementation notes

2026-10-29: pure-side qualification covers explicit start/close, token
permissions and removal, `Host`/`Origin`/token refusal, one endpoint per
runtime, failed-start recovery, busy-deadline withdrawal, reload withdrawal,
client/CLI calls and MCP exclusion (AC 1 and 4). Dispatch is serialized per
runtime: a second call waits or fails with `host_busy` and never runs inside a
handler that pumps a nested event loop. Transport-limit coverage added for
connection overload, absolute read deadlines, truncated/oversized bodies, SSE
capacity, stalled readers and oversized frames. Native reload and stream
teardown qualification (AC 2, 3, 5) is still outstanding.


<!-- SECTION:PLAN:BEGIN -->
Keep the transport hardened: absolute read/write deadlines, bounded connections and SSE buffers, cleanup that survives scheduler failure, and token/reservation release on every failure path. Qualify native dispatch, disconnect cleanup and reload with real QGIS before checking acceptance criteria. Document the endpoint and the MCP boundary in `guides/experimental-plugin-http.md` and `guides/cli-mcp.md`.
<!-- SECTION:PLAN:END -->
