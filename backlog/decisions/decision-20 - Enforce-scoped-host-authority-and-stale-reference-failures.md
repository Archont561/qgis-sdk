---
id: decision-20
title: Enforce scoped host authority and stale reference failures
date: '2026-10-16 09:05'
status: accepted
---
## Context

A broad host bridge (ADR-18) needs concrete resource boundaries. Restricting Python HTTP calls alone does not restrict JavaScript fetch, navigation or embedded resources.

## Decision

Use opaque session-scoped handles for live layers/resources. Validate type, session, existence and permission on each use. Removed layers, foreign/expired handles and replaced runtimes fail explicitly; never silently resolve by matching names. Reconnection reacquires current summaries/handles. Exact session boundaries must be specified consistently with page reload and runtime replacement.

Web views receive filesystem authority through a native picker or explicit plugin grant, with scope for view/session and allowed operation. Do not accept arbitrary frontend paths as authority. Explicit exports require destination/overwrite handling and partial-file cleanup. Canonicalization, symlink/path traversal behavior and grant revocation need security tests.

Per-view host networking restricts destination origins, methods and use of host authentication; validate redirects and private-network access policy and redact credentials. A grant must not become unrestricted fetch. Define request/body limits and permission syntax through further engineering work.

Production WebEngine views also enforce navigation/resource-network restrictions, not just host HTTP authorization. Packaged assets and explicit external origins are the default boundary; local frontend/HMR origins are explicit development exceptions. Qualify the concrete browser controls, redirects, frames, resource requests and page reload behavior on supported Qt/Chromium versions. Do not describe host-only checks as complete egress control or claim a security sandbox without evidence.

## Consequences

- File grants, network grants, browser controls and handle validation are distinct enforcement layers.
- Tests cover stale/foreign handles, denied/redirected destinations, expired grants, filesystem escapes and browser requests bypassing the host API.
- The permission/resource inventory and browser enforcement mechanism remain implementation work; no security guarantee is inferred from declarations alone.

## Mechanisms, settled 2026-10-25

TASK-20 turned the four layers above into code, each one QGIS-free except the
browser, and each one with its own tests. What was open is now fixed:

| Question | Answer | Where it lives |
| --- | --- | --- |
| Caller identity | the host-minted `ViewBinding` (view, origin, generation) reaches every bound handler and stream; JSON claims never do | `bridge.dispatch` |
| Scoped handles | random opaque ids checked against the binding on every use; a foreign or unknown id is `unknown_handle`, said the same way, so a probe learns nothing | `bridge.authority` |
| Stale handles | a replaced generation, an expired TTL, a revocation, or a file that moved or changed identity is `stale_handle`; a read-only ref asked to write is `grant_refused` | `bridge.authority` |
| File authority | a branded `FileRef` minted from a picker result or an explicit plugin grant (one file or a root, `read`/`write`), path canonicalised once, 64 live refs per view; `layers.open_vector` and `files.export` take refs, never paths | `bridge.host`, `bridge.authority` |
| Exports | temp file plus atomic rename next to the destination, 4 MiB ceiling, overwrite only through a `write` grant, partial file removed on failure | `HostAuthority.export_file` |
| Network grant | per view, in one generation: exact http(s) origins, methods (`GET`/`HEAD` by default), host authentication off by default, redirect and body ceilings clamped below the transport's; a hop outside the granted origins is refused before it is issued | `network.grants`, `adapters.qgis.network` |
| Grant syntax | canonical `namespace.method` for operations; `NetworkGrant` fields for the network; no wildcard origins, no suffix matching | `network.grants` |
| Browser egress | `BrowserPolicy`: exact origins (ws/wss fold onto them), `file:` only under resolved asset roots, `qrc:` as packaged content, `data:`/`blob:` as egress-free resources with a `data:` navigation reserved for the host; everything else refused | `adapters.webengine` |
| Browser hooks | `acceptNavigationRequest` for main and sub frames, a page-level request interceptor for every resource, `createWindow` opens nothing, `JavascriptCanOpenWindows` off; Chromium's local-content switches follow the policy and the interceptor confines what they open | `create_restricted_page` |
| Revocation | `revoke(ref)` and `revoke_network(binding)` take effect on the next use; `release_view` forgets a view's refs and grant; `prune(generation)` drops everything older when the runtime is replaced | `HostAuthority` |
| Borrowed release | releasing a borrowed layer drops the view's claim and never reaches the layer; only owned temporary outputs are deleted, exactly once | `bridge.resources` |

Evidence, by route:

- `tests/test_bridge_authority.py`, `tests/test_network_grants.py` and
  `tests/test_bridge_host.py` run in every environment, pip included.
- `tests/test_webengine_policy.py` pins every browser rule without Chromium.
- `tests/test_webengine_native.py` runs a real Chromium offscreen (the TASK-23
  flags) against two loopback origins: the ungranted one is never contacted by
  `fetch`, XHR, `<img>`, `<script>`, `<iframe>`, WebSocket, `location` or
  `window.open`, from a main frame, a subframe or a `file:` page, while the
  granted one keeps serving. It runs in CI's native step.

Two qualification facts shape the browser half and are worth keeping: Chromium
refuses `file:` subresources from a `file:` page before any interceptor runs
unless `LocalContentCanAccessFileUrls` is on, so the restricted page enables it
exactly when the policy names asset roots and lets the interceptor confine the
loads; and Chromium itself refuses a top-frame `data:` navigation from script,
so the policy's rule there is a second lock, not the only one.

What this is not: a sandbox. The policy is an egress allowlist enforced by the
embedding page; it does not claim to contain a compromised renderer, and
nothing in the SDK should describe it that way.
