---
id: TASK-20
title: Enforce scoped file network and browser resource authority
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 23:26'
labels: []
milestone: m-2
dependencies:
  - TASK-24
  - TASK-23
  - TASK-5
references:
  - >-
    backlog/decisions/decision-20 -
    Enforce-scoped-host-authority-and-stale-reference-failures.md
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: medium
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enforce scoped file network and browser resource authority. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Trusted host view/origin/generation binding rejects forged callers; scoped handles fail when stale/foreign.
- [x] #2 Picker/plugin file grants constrain effects and exports; host network grants restrict origins/methods/auth/redirects.
- [x] #3 Real WebEngine navigation/resource tests prevent bypass; define revocation and borrowed-resource release without deleting user layers.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Dispatcher: bound handlers/streams receive the host-minted ViewBinding; refusals raised by an operation carry their own bridge code (unknown_handle, stale_handle, grant_refused); push sources (start/close) so a host can feed a stream without knowing the subscription id; a waker so the channel flushes pushed frames.
2. bridge/authority.py (QGIS-free): HostAuthority mints branded FileRef handles from picker results or explicit plugin grants (read/write/overwrite, canonical path, symlink/traversal refusal, expiry, revocation, per view+generation), holds per-view NetworkGrant (origins, methods, host auth, redirects, body ceiling) and resolves refs on every use against the calling binding.
3. Host surface: layers.open_vector(FileRef), files.export(FileRef, text), network.fetch stream over the TASK-5 transport through the grant; regenerate host.ts (HOST_FINGERPRINT moves, HOST_SCHEMA_VERSION stays).
4. adapters/webengine.py: BrowserPolicy (pure) plus a restricted QWebEnginePage with navigation policy, request interceptor and no popups; real offscreen WebEngine test against two loopback servers (fetch, img, iframe, location, window.open) in CI's native step.
5. Decision amendment recording the settled mechanisms and the release/revocation rules; backlog + doc-4 untouched unless scope changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered on branch arena/9d04e8e8-qgis-sdk in four commits.

Dispatcher (812b515): bound handlers and streams receive the host-minted ViewBinding; operations raise unknown_handle / stale_handle / grant_refused with their own codes; push sources let a host feed a stream; a waker flushes pushed frames.

Authority and grants (e41cd0d): qgis_sdk.network.grants.NetworkGrant constrains or refuses a request (origins, methods, host auth, redirect and body ceilings) and the native transport refuses a redirect hop outside the granted origins before issuing it; qgis_sdk.bridge.authority.HostAuthority mints branded FileRefs from picker results or plugin grants and re-checks every use against the binding (foreign/unknown -> unknown_handle said the same way; replaced generation/expiry/revocation/moved file -> stale_handle; read ref asked to write -> grant_refused); exports are atomic and bounded. Host surface gained layers.open_vector(FileRef), files.export and the network.fetch stream; host.ts regenerated (HOST_FINGERPRINT moved, HOST_SCHEMA_VERSION 1 unchanged); generator renders titled objects, union arrays and number bounds.

Browser (71f6f32): adapters.webengine.BrowserPolicy (pure allowlist) and create_restricted_page (navigation hook, page-level interceptor, no windows, local-content switches follow the policy). test_webengine_policy pins the rules; test_webengine_native drives a real offscreen Chromium against two loopback origins and joins CI's native step.

Qualification facts worth keeping: Chromium blocks file: subresources from file: pages before the interceptor unless LocalContentCanAccessFileUrls is on; Chromium itself refuses script-initiated top-frame data: navigations; a QWebEnginePage must be deleted synchronously (sip.delete) before its profile or the process traps at exit; destroying and recreating an off-the-record profile in one process aborts.

Decision-20 amended with the settled mechanisms, revocation and borrowed-release rules; decision-27 records the second slice; doc-2 section 9 points at them.
<!-- SECTION:NOTES:END -->
