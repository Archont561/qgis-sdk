---
id: TASK-5
title: Add a QGIS-aware HTTP client and typed GIS-service layer
status: Done
assignee: []
created_date: 2026-10-15 23:06
updated_date: '2026-10-25T00:22:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-13
  - TASK-24
priority: medium
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Resolve the proposed networking ADR into one injectable transport respecting QGIS proxy/auth/certificate settings, a generic HTTP client, and typed service clients composed over it. Keep standard WMS/WFS layer loading on QGIS providers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 UI-facing requests are non-blocking by default, with explicit timeout, cancellation, and error semantics.
- [x] #2 A response abstraction provides status, headers, bytes/text/JSON helpers, and explicit status error handling.
- [x] #3 Unit tests use an injected fake transport; QGIS configuration behavior has integration coverage.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on the decision-4 shape. Models: Headers (case-insensitive, redacting repr), NetworkRequest, buffered Response (status_code/reason/headers/content/text/json()/ok/raise_for_status()), DEFAULT_TIMEOUT_SECONDS=30, DEFAULT_MAX_REDIRECTS=20, DEFAULT_MAX_BODY_BYTES=16 MiB; QgisSdkNetworkError family classified by code (request_rejected, request_cancelled, connection_failed, request_timeout, tls_failed, authentication_failed, redirect_refused, response_too_large, http_status, decode_failed, blocking_on_gui_thread, service_response_invalid). Services: NetworkTransport(send/send_blocking), Network, BlockingNetwork; PluginContext/UiContext.network + require_network(). Client: qgis_sdk.network.NetworkClient (coroutine get/post/request awaiting a scheduling Handoff; configure() derives immutable clients; .blocking refuses the GUI thread; scope close cancels in flight) and OgcApiFeatures as the first typed service. Scheduling: Handoff(on_cancel=) so Job.cancel() reaches the transport while the job is suspended. Adapter: adapters.qgis.NativeNetworkTransport over QgsNetworkAccessManager with ManualRedirectPolicy and its own redirect loop (credentials and auth_config dropped on origin change, https->http refused, 303/POST->GET), per-request QTimer timeout, downloadProgress body-ceiling abort, authManager().updateNetworkRequest for auth_config, cross-thread cancel via queued signal, blocking form under a local QEventLoop. Testing: qgis_sdk.testing.FakeNetworkTransport (scripted, fails unexpected requests, hold/deliver, never opens a socket) + reply().

Measured numbers (doc-15, scripts/network_limits_probe.py, QGIS 4.2.3/Qt 6.11.2 offscreen, 4 runs): the manager follows 50 redirects unaided under NoLessSafeRedirectPolicy and forwards Authorization and Cookie to another origin, so the transport follows redirects itself; a transport hop costs 0.66-1.18 ms, so the browser limit of 20 stands. Finish stall of a buffered body: 16 MiB 13-15 ms, 32 MiB 40-44 ms (straddles the 40 ms GUI budget from doc-6), 64 MiB 78-83 ms; ceiling set to 16 MiB. Coverage: QGIS-free tests test_network_{models,client,ogc,fake}.py + scheduling cancellation tests + tests/scripts/test_network_limits_probe.py; native tests/test_network_native.py (25, loopback servers: coroutine/blocking forms, timeout vs cancel, scope close, body ceiling, redirect rules, QGIS proxy setting, Basic auth configuration from a throwaway auth DB, untrusted vs QGIS-trusted self-signed TLS). CI step s11 now also runs the native network file. Not done here: wiring ctx.network into the scaffold's build_context (host composition; the guide shows the two lines), and bridge networking (TASK-20, deny-by-default).

Closed: merged to main via PR #57 (merge commit 7e1bbb9, route gh pr merge --merge) with CI green, including the native loopback-server suite in the offscreen step; all three acceptance criteria checked on the merged change. (The original closure was recorded on the merged session branch only; re-applied on 2026-10-25 so main carries it.)
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 16:54
---
Moved from m-1 to m-2 on 2026-10-24 during the 0.2.0 re-scope. 0.2.0 closes on TASK-3 + TASK-28: this task blocked nothing inside m-1, sits outside the 'native runtime and Processing' surface the milestone is named for, and its networking transport still needs decision-4 resolved, which is only proposed. TASK-29 does not close until this lands, so it cannot slip silently.
---

author: qgis-sdk agent
created: 2026-10-24 17:02
---
decision-4 is now accepted (2026-10-24), so this task implements a settled design rather than resolving one. The API is fixed in the decision: one injected ctx.network client with get/post/request, immutable derived clients, a fully buffered Response, coroutine methods as the UI-facing form, and a blocking form that refuses GUI-thread use. Two numbers stay task-level and must come from measurement here, not from the decision: the redirect limit and the buffered body-size ceiling.
---
<!-- COMMENTS:END -->
