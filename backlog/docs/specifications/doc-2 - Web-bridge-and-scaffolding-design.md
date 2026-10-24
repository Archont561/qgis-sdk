---
id: doc-2
title: Web bridge and scaffolding design
type: specification
created_date: '2026-10-16 08:37'
updated_date: '2026-10-16 09:11'
---
# Web bridge and scaffolding design

**Status:** Confirmed direction from the 2026-10-16 clarification interview; API names, source layout and CLI flags below are illustrative. The current TypeScript package is a smoke-test scaffold, not this implementation. Acceptance of policy is not platform qualification or feature completion.

## 1. Runtime boundaries

Keep the bridge framework-neutral with isolated areas for protocol values/errors/capabilities, transport contracts and QWebChannel integration, calls/events/connection lifecycle, curated host facades, optional React helpers and testing utilities. Start in one package with isolated subpath exports; split distributions only if dependency/release needs justify it. Root imports must not load React/testing, access window or create a connection. Native-only Python plugins do not require this package.

One transport owns one shared QWebChannel. Component mounts do not create channels independently. Define connect/readiness/handshake, failed initialization, timeouts, request correlation, disconnect/reconnect and disposal. Distinguish full frontend page reload from Python plugin runtime replacement; invalidate stale runtime generations and handles. Framework adapters own their subscriptions, not independent transports.

## 2. Public API surfaces

- Connection lifecycle: explicit creation/connection/disposal and observable status.
- Generated plugin client: typed named operations, request/result models, events, error metadata, validators and contract identity derived from Python declarations.
- Broad host capabilities: layers, project, notifications, settings, Processing, jobs and networking, only through per-view grants. This is a capability inventory, not a finalized list of callable methods.

Host-side authorization denies access by default, including empty allowlists. Define read/write scopes and operation/resource constraints (including network destinations and allowed Processing algorithms). Never expose arbitrary native objects, generic Python invocation, unrestricted files or credentials. Unauthorized/unavailable calls fail explicitly rather than returning plausible empty values. The frontend may use capabilities for presentation but cannot enforce security itself.

Protocol compatibility is versioned: reject incompatible changes and permit only explicitly classified compatible additions. Fingerprints identify drift, not compatibility. Before implementation, define unknown-field behavior, required-input changes, output evolution, event evolution and capability negotiation tests.

## 3. Framework adapters

Ship vanilla TypeScript and React initially. React provides typed context/provider access, connection state and event/subscription lifecycle helpers. Development remounts must not leak or duplicate channel state. Vanilla uses the same generated client directly. Vue/Svelte templates/adapters are deferred rather than implied by the architecture.

Do not build a separate wire API per framework or a bespoke query-cache framework initially. Hooks/composables consume the common client; external query/cache integrations can follow demonstrated demand. React peer dependencies are optional and isolated from the root import.

## 4. Type generation

Python registered endpoints and ordinary dataclasses produce a validated API description with separate input-validation and output-serialization schemas. From that derive TS DTOs, operation maps, callable wrappers, event types, runtime validators and contract identity. Injected host dependencies are absent from public request models. Unsupported annotations produce errors, not any. Distinguish nullable, omittable and defaulted fields and define numeric/date/binary representations.

Check generated TypeScript bindings into plugin projects, mark them generated and enforce deterministic regeneration/drift checks in CI. Generated wrappers call one shared runtime; do not duplicate correlation/reconnection logic per operation. Generation is deterministic, supports stale-file checks and runs without QGIS/handlers. dev coordinates generation with backend replacement so old/new incompatible contracts do not call each other. build validates packaged bindings against the backend. File ownership is explicit; generated files are not hand-edited.

Run a backend compatibility spike (ADR-10) before selecting validation implementation. Pure-Python-first runtime packaging is a constraint; choosing mandatory native validators requires a separate explicit decision.

## 5. Testing utilities

Provide a typed fake host/client harness for application tests: explicit handlers, captured calls, scripted results/errors/delays, event emission, capabilities, disconnect/reconnect, cancellation and deterministic scheduling. Unexpected calls fail and teardown detects unmet expectations/subscription leaks. Never auto-enable mocks because a frontend is outside QGIS; an explicit preview mode labels fake data.

Provide a separate protocol transport harness: malformed envelopes/results, duplicate/missing/late responses, unsupported versions, expired/foreign handles, old-generation events and shared-channel consumers. Python and TS independently validate common versioned contract fixtures. Use property-based tests for protocol/state invariants, compile-time tests for generated APIs, React lifecycle tests and a small real QWebEngine suite. Browser mocks do not prove Qt native behavior.

Generated vanilla/React projects use Vitest with npm/pnpm/Bun launching the same runner. This does not migrate the SDK repository's existing Bun test tooling implicitly. Property-test and component-test library choices are still open.

## 6. Scaffold plan and questionnaire

new plugin supports native, web, both or no UI; web offers vanilla TypeScript/React, dialog/dock and npm/pnpm/Bun. Vite builds/serves all generated web apps. Bunup is relevant to reusable TS/component-library scaffolds, not selected merely because Bun is the package manager. Support for a future library scaffold is not a required v1 command.

Interactive answers, explicit flags and any supported configuration input resolve to one validated options model and file-generation plan. Ask only applicable questions; reject incompatible combinations and missing required non-interactive choices. Never wait for a prompt when stdin is non-interactive. Installation is opt-in: ask interactively or require an explicit --install-equivalent flag. Do not install system/QGIS toolchains implicitly.

Templates are reviewed/version-controlled, not arbitrary latest remote generators. Keep shared backend/contract/bootstrap generation separate from framework entry components, dependencies, build commands and starter tests. Validate names/path containment, show/refuse collisions, avoid destructive config merging when adding a view, and preserve generated source plus a retry command after optional install failure.

Illustrative layout:

```text
plugin-project/
  pyproject.toml
  qgis-sdk.toml
  src/plugin_package/
    plugin.py
    api/
    views/
  tests/
  web/
    package.json
    vite.config.ts
    src/
      generated/
      bridge.ts
      main.ts or main.tsx
      App.tsx (React only)
    tests/
```

Generated config records API entry points/output, frontend commands, production asset directory, package manager and browser build targets. Browser targets must match the qualified QGIS Chromium runtimes, not assume latest-browser features. Include a small working endpoint, view and test rather than a large unexplained template.

## 7. Development and build integration

dev starts the frontend server only for web UI and uses constrained local origins. Frontend HMR preserves Python state; full page reload reconnects/handshakes/resubscribes. Python refresh follows ADR-15: preflight, quiesce, finish/cancel owned work safely, dispose, replace plugin modules, construct new generation and restore serializable presentation state. Automatic refresh is enabled only after lifecycle tests prove it safe.

build runs shared checks, generates consistent bindings, compiles production assets and bundles a private pure-Python-first runtime (ADR-3). It never leaves a dev server dependency in the artifact or silently runs tests/publishes. Validate dialog and dock installation/startup/unload in actual qualified environments.

## 8. Qualification and open implementation work

First release target: QGIS 4, Windows/Linux x86-64, explicit tested builds starting from the workspace's QGIS 4.2.3 where suitable installations exist. No claim that either platform or every 4.x is already qualified. Rust shipping/custom tooling, macOS, Vue/Svelte and broad native dependency vendoring are deferred.

Open work: exact host operation inventory, constrained-grant syntax, protocol compatibility algorithm, async/Qt scheduler spike, dataclass backend spike, precise generated exports/commands, questionnaire implementation, template/browser baseline matrix and public API stability/deprecation rules. The v1 job subset and exact per-service semantics still need specification. None is silently settled by sample code.

## Related decisions

- [decision-3](../../decisions/decision-3%20-%20Development-and-distribution-artifacts-are-separate.md)
- [decision-4](../../decisions/decision-4%20-%20QGIS-aware-networking-uses-an-async-first-transport.md)
- [decision-5](../../decisions/decision-5%20-%20Rust-algorithm-implementations-are-post-v1-and-backend-neutral.md)
- [decision-7](../../decisions/decision-7%20-%20Use-layered-pytest-fixtures-properties-and-behavioural-contracts.md)
- [decision-9](../../decisions/decision-9%20-%20Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md)
- [decision-10](../../decisions/decision-10%20-%20Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md)
- [decision-12](../../decisions/decision-12%20-%20Use-one-context-injected-controller-per-UI-surface.md)
- [decision-13](../../decisions/decision-13%20-%20Use-runtime-bound-Celery-inspired-local-jobs.md)
- [decision-15](../../decisions/decision-15%20-%20Refresh-development-through-owned-runtime-generations.md)
- [decision-17](../../decisions/decision-17%20-%20Deliver-a-qualified-Python-first-vertical-slice-for-v1.md)
- [decision-18](../../decisions/decision-18%20-%20Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md)


## 9. Confirmed second-interview boundary policies

Requests reject unknown fields and implicit coercion by default; compatible result readers validate required known fields and tolerate only defined additive extensions. Do not conflate request strictness with result extensibility. Translate expected typed errors to stable codes/details; unexpected errors keep detailed redacted host logs and expose safe correlation IDs, not raw tracebacks.

Layer/resource handles are opaque and scoped; removal, expiry or foreign sessions fail explicitly. File authority comes from native pickers or explicit grants. Constrain per-view network origins/methods/auth use/redirects and enforce separate real-browser navigation/resource restrictions so direct fetch/embedded resources do not bypass the policy. The concrete controls are settled in decision-20's 2026-10-25 amendment: `HostAuthority` mints and re-checks `FileRef` handles and holds the per-view `NetworkGrant`; `BrowserPolicy` plus `create_restricted_page` enforce browser egress, qualified against a real offscreen Chromium in CI.

Default view-owned jobs detach callbacks and request cancellation on disposal (not hiding); initial jobs have no automatic retries. Non-terminating owned work blocks in-process reload and requires explicit restart, rather than forced deletion. Generated bindings are checked in with CI drift checks. Experimental 0.x releases carry migration notes. A failed async spike requires explicit scope revisiting, not a silently preauthorized fallback.

See [decision-20](../../decisions/decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md), [decision-21](../../decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md), [decision-22](../../decisions/decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md) and [doc-3](doc-3%20-%20Reference-workflow-and-runtime-safety-acceptance.md).


## 10. Proposed lessons from Tauri IPC invoke

Source reference: tauri-apps/tauri commit `136a28eaa879e8aa706f9b2e05a050c46dcc1f4f`; inspection only, no execution. Adapt architecture patterns to QWebChannel, not Tauri runtime internals or a Rust dependency.

| Reference idea | Proposed QGIS adaptation | Evidence required |
| --- | --- | --- |
| One invoke primitive | Small shared invocation kernel under generated typed methods | Compile-time invalid-name/input/result tests and malformed-result runtime tests |
| Host command resolution | Narrow transport endpoint and Python dispatcher with trusted view/origin/generation | Forged caller IDs cannot select another view's permissions; no direct-object bypass |
| Channels vs events | Separate operation progress/data streams from state subscriptions and single replies | Ordering, terminal state, gaps/overflow bounds, disposal/reconnect and subscriber-failure tests |
| Explicit resources | Release references/subscriptions separately from deleting owned temporary resources | Borrowed-layer release preserves the project layer; repeated/in-flight close is defined |
| IPC mocks | Inject a fake transport into each client | Isolation between clients, unexpected-call failures, scripted events/errors and leak assertions |
| Async frontend API | Promise waiting is distinct from host execution/cancellation | Local abort/timeout cannot falsely acknowledge host cancellation or trigger automatic retry |

The dispatcher consistently handles registry lookup, authorization/resource scope, validation and safe result/error serialization. Trusted caller identity comes from host-owned endpoint/session state, not JSON claims. Generated clients improve on manually asserting invoke<Result>; schema validation remains required at runtime.

Logical stream channels are not QWebChannel instances. Ordered delivery does not provide bounded memory or flow control. Choose limits, overflow/gap behavior and any progress coalescing explicitly; do not silently drop stream data. Completion, cancellation and view/runtime disposal must release callbacks/resources independently of JS garbage collection.

Resource methods distinguish borrowed handles, subscriptions and owned temporary outputs. Releasing a layer reference must not delete user data. Native cleanup and GUI-thread delivery remain host responsibilities. Tauri's binary transport and Rust drop behavior are reference details, not promised QGIS capabilities.

Keep the shared client framework-neutral and avoid global mocks as a requirement. Native tests separately prove QWebChannel registration, caller binding and cleanup; pure/React/Vitest tests prove only their respective contracts. Existing accepted security, packaging and deferred-Rust policies remain unchanged.

Proposed architecture details: [decision-23](../../decisions/decision-23%20-%20Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md). Implementation tracking: TASK-4 and TASK-7.
