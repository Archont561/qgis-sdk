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