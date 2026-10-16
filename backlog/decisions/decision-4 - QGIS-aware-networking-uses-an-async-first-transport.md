---
id: decision-4
title: QGIS-aware networking uses an async-first transport
date: '2026-10-15 23:05'
status: proposed
---
## Context

Plugins need both general HTTP operations and typed clients for GIS services. Requests made by a plugin should respect QGIS proxy, authentication, and certificate configuration. UI-triggered network activity must not block the QGIS event loop, while tests need deterministic transport fakes. WebEngine code also needs a deliberately constrained bridge rather than direct access to Qt network objects. The inspected `qgis-rust` network API offers useful requests-inspired conveniences and QGIS-aware transport ideas, but its overlapping `Session`/`NetworkManager`/`NetworkAccessManager` public abstractions and blocking-by-default request behavior are not a target API.

## Decision

Proposed: provide one injectable, QGIS-aware transport/client as the shared foundation for a generic requests-inspired HTTP API and typed GIS-service clients. Prefer QGIS network facilities/settings, expose a response abstraction with status, headers, bytes/text/JSON and `raise_for_status`-style error handling, and make UI-facing requests asynchronous by default; blocking calls must be explicit. Compose typed clients over the shared transport rather than exposing overlapping public session/manager wrappers. Use QGIS layer/provider APIs for ordinary WMS/WFS layer loading. Tests inject a fake transport. Any JavaScript bridge networking is opt-in, permissioned, and returns serializable DTOs only.

## Consequences

- The API must define cancellation, timeout, error, response-body, and event-loop behavior.
- Transport fakes and service-client contract tests should not require a live endpoint.
- QGIS auth/proxy behavior and supported QGIS versions need integration tests.
- The generic client is not a replacement for QGIS providers when the desired result is a QGIS layer.
- This decision remains proposed until the public async API and ownership/lifecycle model are agreed.

## Proposed service boundary refinement (2026-10-16)

Expose networking through an injected service contract on PluginContext, implemented by the QGIS adapter and separately by scripted test fakes; see [decision-6](decision-6%20-%20Separate-models-services-core-and-runtime-adapters.md) and [decision-7](decision-7%20-%20Use-layered-pytest-fixtures-properties-and-behavioural-contracts.md). Keep invocation cancellation/progress separate from plugin-lifetime service state. A coroutine/Promise is not evidence of non-blocking execution: define the Qt scheduling integration and GUI-thread handoff before committing to async handler syntax. Bridge access is explicitly permissioned and deny-by-default, with DTO responses and no automatic native-to-fake fallback ([decision-9](decision-9%20-%20Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md)).

## Proposed requests-like client refinement (2026-10-16)

Expose one injected ctx.network client with familiar get/post, params/json/data/headers/timeout options and response status_code/headers/content/text/json()/raise_for_status(). Derive immutable configured clients rather than mutate global defaults. Define mutually exclusive body options, text decoding, redirects and body-size limits. Fully buffered response values are the initial proposal; explicit download/streaming follows real need. Never expose live QNetworkReply objects.

UI-originated operations are non-blocking, but await examples remain illustrative until Qt-compatible scheduling is specified. Explicit blocking operations are only supported in suitable execution contexts and must reject unsafe GUI-thread use rather than nest an event loop. Own requests by view/plugin/algorithm/job scope and prevent callbacks into disposed owners. Distinguish cancellation, connection/timeout/TLS/auth/status and decode errors. Prefer QGIS auth-configuration references, redact credentials, and avoid forwarding credentials across unrelated redirect origins. Typed service clients compose over HTTP; ordinary WMS/WFS layers still use QGIS providers. Scripted fakes fail unexpected requests and never silently contact the internet.

## Confirmed constraints and open scheduler work (2026-10-16)

The user chose synchronous GUI-safe handlers plus coroutine/non-blocking operations subject to a Qt-compatible scheduler spike, not unrestricted worker-thread execution. Validate cancellation, disposal and GUI-thread handoff on the target Windows/Linux matrix before finalizing async syntax. The broad web host surface includes networking, with host-enforced per-view authorization. Scheduler implementation, request limits and destination-grant syntax remain open. Packaging follows ADR-3; Rust remains deferred by ADR-5.
