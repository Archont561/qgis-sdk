---
id: TASK-74
title: >-
  Expose opted-in plugin actions and streams over an explicitly hosted loopback
  REST API for clients outside QGIS
status: In Progress
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-29 13:34'
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
- [x] #2 An allowlisted action dispatches on the QGIS owner thread; a queued call past its deadline fails with the documented busy error and is withdrawn before it can run, and a reload fails in-flight calls with the host-reloaded error without running withdrawn work (pure and native tests).
- [x] #3 Streams deliver ordered SSE frames, honour the event-stream capacity limit, bound frame size and buffered bytes, and dispose their subscription on client disconnect or server close (pure and native tests).
- [x] #4 The Python client and CLI call a live plugin and stream events without importing the runtime; the CLI MCP inventory contains no plugin REST commands (tests at the public seams).
- [x] #5 Real QGIS qualification covers owner-thread dispatch and teardown/reload, the built plugin vendors `qgis_sdk.http` only on explicit import, and no `qgis_sdk.agent` module, agent checker, guide or test remains.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-29: pure-side qualification covers explicit start/close, token
permissions and removal, `Host`/`Origin`/token refusal, one endpoint per
runtime, failed-start recovery, busy-deadline withdrawal, reload withdrawal,
client/CLI calls and MCP exclusion (AC 1 and 4). Dispatch is serialized per
runtime: a second call waits or fails with `host_busy` and never runs inside a
handler that pumps a nested event loop; a call from the thread already running
work is refused at once. Transport-limit coverage covers connection overload,
absolute read deadlines, truncated/oversized bodies, SSE capacity, stalled
readers, oversized frames and the aggregate frame-buffer bound.

Native qualification (AC 2, 3, 5) is in `test_zz_plugin_rest_native.py`: an
action dispatches on the real QGIS owner thread; a nested `QDialog.exec()`
queues a second call and never re-enters it (verified by forcing posted work to
run inside the dialog); a 40-frame stream is produced entirely on the owner
thread and ends with a terminal frame; reload during a dialog fails the
in-flight call with `host_reloaded` and disposes the live stream only after the
dialog returns; close during a dialog keeps the runtime reserved until the
action unwinds; an off-owner close disposes a live stream on the owner thread
and removes the token. Each was checked against a deliberately broken
implementation to confirm the test fails.

<!-- SECTION:PLAN:BEGIN -->
Keep the transport hardened: absolute read/write deadlines, bounded connections and SSE buffers, cleanup that survives scheduler failure, and token/reservation release on every failure path. Qualify native dispatch, disconnect cleanup and reload with real QGIS before checking acceptance criteria. Document the endpoint and the MCP boundary in `guides/experimental-plugin-http.md` and `guides/cli-mcp.md`.
<!-- SECTION:PLAN:END -->

2026-10-29 scope decision (POSIX only): creating the token file relies on POSIX permissions, and Windows credential storage is not implemented. Rather than start a listener whose token another local account could read, PluginHttpServer.start() refuses on a non-POSIX platform with a QgisSdkHttpError that names the limitation and leaves no token or listener. test_start_refuses_a_platform_without_private_token_permissions pins the refusal and proves it does not consume the runtime, so the same server starts once the check passes. The boundary is documented in guides/experimental-plugin-http.md and the 0.8.0 migration notes (doc-12). This is a deliberate scope decision for 0.8.0, not an unfinished fix.
<!-- SECTION:NOTES:END -->
