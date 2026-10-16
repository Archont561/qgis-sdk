---
id: decision-17
title: Deliver a qualified Python first vertical slice for v1
date: '2026-10-16 08:37'
status: accepted
---
## Context

The design discussion proposed many capabilities without a firm first-release boundary. The user confirmed the following scope and support policy in the clarification interview on 2026-10-16. Acceptance records direction, not completed implementation or platform qualification.

## Decision

Deliver one complete reference-plugin workflow: plain Python plugin/algorithm/UI classes with scoped injected contexts, native and web UI paths, typed bridge/generated clients, pure and selected native integration tests, new/check/test/dev/build, and the minimal local-job functionality needed by the workflow. Advanced orchestration and comprehensive wrappers/styles are not prerequisites. The web path includes vanilla TypeScript and React, dialogs and docks.

Target QGIS 4 on Windows x86-64 and Linux x86-64 using an explicit tested matrix. QGIS 4.2.3 is the current development starting point, not proof that Windows/Linux installations are qualified or that all 4.x releases work. Record actual QGIS/Python/Qt/platform builds and evidence before claiming support. QGIS 3, macOS and other architectures require later qualification.

Keep authoring Python-only in v1 and defer shipping Rust, including SDK-owned Rust acceleration. Use existing QGIS/native capabilities first. Compute interfaces remain implementation-neutral and are added for concrete workflows, not to justify a speculative backend framework. Later acceleration needs benchmark and packaging evidence; custom Rust scaffolding is also deferred.

## Consequences

- One example must run through scaffold, tests, development and plugin ZIP installation instead of releasing disconnected partial APIs.
- Native Processing, bridge, reload and build behavior still need native qualification; a passing pure test or developer sandbox restore is not that evidence.
- Public names, minimal job details, precise supported builds and scheduler/validator choices remain open engineering work.

## Confirmed second-interview refinement (2026-10-16)

[decision-19](decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md) defines the local-GIS reference workflow; [decision-22](decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md) clarifies that initial public releases are experimental 0.x, and a failed async spike triggers an explicit scope revisit rather than an assumed fallback.
