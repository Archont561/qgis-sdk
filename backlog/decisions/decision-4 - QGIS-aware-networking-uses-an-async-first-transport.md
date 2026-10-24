---
id: decision-4
title: QGIS-aware networking uses an async-first transport
date: '2026-10-15 23:05'
status: accepted
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

## Status review (2026-10-24)

**Promoted to `accepted`.** The condition the decision set for itself - "remains
proposed until the public async API and ownership/lifecycle model are agreed" -
is now met, and the Decisions above are the specification rather than a sketch.

What settled it:

- **The scheduler clause is closed.** The `await` examples were called
  illustrative "until Qt-compatible scheduling is specified". It is specified:
  the StepScheduler spike landed with its qualification evidence
  ([doc-6](../docs/plans/doc-6%20-%20TASK-13-Qt-scheduler-spike-evidence.md)), and
  `qgis_sdk.core.scheduling` is the implementation TASK-5 composes with. Nothing
  in the networking surface depends on an unspecified handoff any more.
- **The ownership model exists.** Requests are owned by the scope that started
  them ([decision-21](decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md))
  and released through `ResourceScope`, which is already implemented; the
  "prevent callbacks into disposed owners" requirement is therefore a rule over
  an existing mechanism, not a promise.
- **The shape is no longer ambiguous.** One injected `ctx.network` client, not a
  `Session`/`NetworkManager` pair: `get`/`post`/`request` with
  `params`/`json`/`data`/`headers`/`timeout`, immutable derived clients instead
  of mutated global defaults, a fully buffered `Response` exposing `status_code`,
  `headers`, `content`, `text`, `json()` and `raise_for_status()`. Coroutine
  methods are the UI-facing form; a blocking call is explicit, allowed only off
  the GUI thread, and refuses GUI-thread use rather than nesting an event loop.
  Live `QNetworkReply` objects are never exposed.
- **Errors are classified** - cancellation, connection, timeout, TLS,
  authentication, status and decode - as `QgisSdk*` codes, so a caller can tell a
  retryable failure from a terminal one without parsing strings
  ([decision-22](decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md)).
- **Bridge access stays denied by default** and returns serializable DTOs only
  ([decision-9](decision-9%20-%20Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md),
  [decision-20](decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md)).

What this does **not** claim: no networking code exists yet. TASK-5 (now m-2)
implements this decision, and its acceptance criteria - not this record - are
where execution gets proven. Two implementation details remain task-level and
deliberately unnumbered here: the concrete redirect limit and the buffered
body-size ceiling, both of which TASK-5 must set from measurement rather than
guess.
