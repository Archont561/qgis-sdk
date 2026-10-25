---
id: TASK-18
title: Add thin React bindings and isolated frontend test harnesses
status: Done
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T00:22:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-4
  - TASK-17
references:
  - >-
    backlog/decisions/decision-18 -
    Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: medium
type: feature
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add thin React bindings and isolated frontend test harnesses. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Root imports stay framework/browser-global free; vanilla and React consume the same typed client.
- [x] #2 Provider/remount/dispose tests prove shared connection ownership and no leaked subscriptions.
- [x] #3 Injected per-client harnesses script typed calls/events/faults, fail unexpected calls and separate mock evidence from native tests.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on the session branch (PR to follow). AC #1: src/react.ts is the only module importing react (optional peer >=18, external in bunup); tests/surface.test.ts scans index/bridge/host/generated host for imports and browser globals and bundles them with Bun.build asserting no 'react'. tests/react.test.ts 'vanilla and React consume the same generated client' drives createOperations once from a plain call and once from useOperation over one BridgeClient. AC #2: BridgeProvider owns a client per mount (created in an effect, closed on unmount; StrictMode remount replaces it and leaves one transport listener), injected clients are left alone; useStream closes on unmount, on input change, on null input, after a late ack, and StrictMode leaves exactly one open subscription - all asserted via harness.listeners/openSubscriptions/calls. AC #3: src/testing.ts createBridgeHarness<Op>() is a WireTransport injected per client: typed expectInvoke/expectSubscribe FIFO per op, fault()/SILENCE, ScriptedStream emit/end/skip (gap), ordered microtask outbox, unexpected calls answered unexpected_call and reported, assertSatisfied() reports unmet/unexpected/open/handler throws as QgisSdkBridgeHarnessError; two harnesses prove isolation. Mock evidence boundary documented in doc-13 (React bindings, Testing against a scripted host) pointing at doc-14 for native evidence. Bridge gate green: bun test 181 pass, coverage 96% lines, typecheck, biome, generate --check.

Closed: merged to main via PR #57 (merge commit 7e1bbb9, route gh pr merge --merge) with CI green; all three acceptance criteria checked on the merged change. (The original closure was recorded on the merged session branch only; re-applied on 2026-10-25 so main carries it.)
<!-- SECTION:NOTES:END -->
