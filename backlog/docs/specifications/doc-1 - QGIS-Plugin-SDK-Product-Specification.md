---
id: doc-1
title: QGIS Plugin SDK Product Specification
type: specification
created_date: '2026-10-15 23:04'
updated_date: '2026-10-16 12:02'
---
# QGIS Plugin SDK Product Specification

**Status:** Working specification, updated from the 2026-10-16 design discussion. ADRs 1, 2, 3, 5 and 17–22 are accepted; ADR-4 and ADRs 6–16 remain proposals, with confirmed constraints cross-referenced. Acceptance is a design decision, not evidence of implementation. All example module/API names and CLI flags are illustrative until implemented. This document describes intended behavior, not existing capabilities or a promise that every feature ships in v1.

## 1. Purpose and users

Provide a Python-first SDK and toolchain for authoring, developing, testing, building, and distributing QGIS plugins. The primary user is a Python developer who wants a repeatable plugin structure, a declarative UI layer where useful, a fast development loop, and installable QGIS output without hand-assembling runtime files.

The SDK should support both conventional QGIS plugins and plugins that use a web UI, without requiring every plugin to use QWebEngine or TypeScript.

## 2. Product principles

1. **Python owns plugin behavior.** Decorators and typed declarations describe plugin/UI structure; normal Python methods implement behavior. See [decision-1](../../decisions/decision-1%20-%20Python-declarative-API-is-the-plugin-authoring-source.md).
2. **One derived description contract.** Tooling and UI renderers consume an inspectable description derived from Python. JSON is generated/interchange, not independently authored truth. See [decision-2](../../decisions/decision-2%20-%20The-plugin-description-is-the-shared-schema-contract.md).
3. **QGIS is the runtime authority.** Prefer a QGIS executable available on `PATH` or a QGIS/PyQGIS installation importable by the selected Python environment. Do not require the SDK workspace's Pixi-pinned QGIS runtime as the only supported runtime.
4. **Differentiate runtime contexts.** A pure PyQt application, even one that initializes PyQGIS and embeds `QgsMapCanvas`, is not equivalent to a QGIS Desktop plugin. Features requiring `iface`, plugin discovery, or the plugin lifecycle must run in QGIS Desktop.
5. **Keep authoring and installation artifacts distinct.** `pip install qgis-sdk` is for developers; the build output is a QGIS-installable plugin archive. Each plugin bundles its required runtime privately; a separate shared runtime installation is not required in v1 (ADR-3).
6. **Make tests layerable.** Pure description/logic tests should not require QGIS; Qt, QGIS, Desktop, and WebEngine integration tests may opt into progressively heavier runtimes.

## 3. Authoring and runtime model

### 3.1 Python API

The Python package is the authoring API and runtime entry point. It should provide compact, typed declarations/decorators for plugin identity, actions, UI surfaces, fields, and event bindings. Decorators attach inspectable metadata; handler methods contain behavior and can use normal Python control flow and types.

The SDK derives a validated plugin description from those declarations. The description contains only supported, serializable structure: stable identifiers, display metadata, field types/constraints, actions, view declarations, and binding names. It must not serialize callables, arbitrary object graphs, secrets, or live QGIS objects. A versioned JSON representation may be emitted for the TypeScript/WebEngine consumer and diagnostics.

The runtime maps user input and events to Python handlers, validates values at the boundary, and reports errors through a consistent plugin-facing mechanism. Dynamic Python behavior remains Python behavior; generated descriptions are not expected to encode arbitrary program logic.

### 3.2 UI modes

- **Native Qt/QGIS UI:** Use PyQt/QGIS widgets and services. Declarative descriptions may drive common forms/actions while Python handlers remain authoritative.
- **Web UI:** Optional QWebEngine view with a typed QWebChannel bridge. The bridge is an allowlisted API and exchanges versioned serializable DTOs. Do not expose `iface`, Qt objects, raw replies, or arbitrary Python invocation to JavaScript.
- **Standalone PyQt/PyQGIS:** May be useful for canvas-centric apps after initializing PyQGIS, but does not provide the actual QGIS Desktop `iface` or plugin lifecycle.

## 4. User workflows and CLI surface

The intended CLI flow is:

1. `qgis-sdk new plugin <name>` creates a minimal plugin package, entry point, tests and optional UI assets; algorithm/UI scaffolds may follow.
2. `qgis-sdk check` checks source configuration, declarations, metadata, assets and dependency-policy consistency without QGIS or source mutation by default. It does not install dependencies, build assets or execute the test suite.
3. `qgis-sdk test` is an environment-aware pytest launcher: pure tests by default, explicit real-QGIS/Desktop targets, pytest arguments after `--`, visible runtime selection and preserved exit status. Direct pytest remains supported. A requested unavailable runtime is a failure, not a silently skipped green gate; pure collection must exclude native-only imports.
4. `qgis-sdk dev` launches real QGIS Desktop by default with an isolated development profile and source plugin; standalone/preview targets are explicit and reduced-capability.
5. API generation derives frontend bindings/validators from Python declarations and supports deterministic output and stale-file checks. Exact command spelling remains open.
6. `qgis-sdk build` runs shared source checks, generates adapters, builds optional frontend assets, stages runtime/resources and validates a QGIS-installable ZIP. It does not implicitly run tests, install or publish. Optional requested native verification must fail if the required runtime is unavailable.

These command names express the intended workflow; exact flags, project layout, and command compatibility remain implementation/API decisions.

## 5. Development mode

`qgis-sdk dev` should support two distinct targets/configurations:

- **Desktop plugin mode:** locate QGIS Desktop through `PATH` or explicit configuration, create/use an isolated QGIS profile where practical, expose the source plugin through QGIS plugin discovery, and load it in the real plugin lifecycle. This is required to test `iface` and Desktop integration.
- **Standalone Qt mode:** launch a configured PyQt/PyQGIS application when a plugin needs Qt/canvas functionality but not the Desktop plugin lifecycle. Clearly identify the reduced capability set.

For WebEngine plugins, start the frontend dev server only when the selected plugin has a web UI. The QWebEngine view should load the local dev origin so frontend changes use the frontend tool's HMR. Python changes should trigger a controlled plugin reload/view recreation and bridge reattachment; if safe in-process reload is not reliable for a particular change, the tool should report that and offer/recommend a QGIS restart rather than silently leave stale handlers loaded. Production builds use compiled web assets, not the development server. Remote WebEngine debugging is opt-in.

The dev server should bind only to loopback by default. The bridge should remain constrained to the plugin's declared API and the local development origin.

## 6. Testing and quality gates

Support progressively heavier test layers:

1. **Pure Python:** declarations, description generation/validation, utilities, and handler logic with injected dependencies. Runs without QGIS.
2. **Qt:** widget behavior and signal/slot integration under a Qt test application; skip or isolate tests requiring a display where supported.
3. **QGIS runtime:** provider, processing, project, and PyQGIS behavior under an initialized QGIS runtime, with fixtures for lifecycle setup/teardown.
4. **Desktop plugin integration:** plugin discovery, `iface`, menus/actions, and lifecycle in actual QGIS Desktop where needed.
5. **Web/bridge contract:** shared request/response/error fixtures and bridge tests across Python and TypeScript; test DTO serialization and permission boundaries.

Provide injectable fakes for external services and QGIS-dependent collaborators. Use `pytest-bdd` where behavior benefits from readable scenario specifications, while retaining ordinary pytest tests for lower-level cases. Avoid making all tests depend on a full Desktop install. The repository declares and locks pytest-bdd and Hypothesis; their presence does not mean these fixture layers or SDK contracts are implemented.

## 7. Networking and GIS services

The intended API has one shared injectable transport that respects QGIS networking configuration (proxy, authentication, and certificates), a generic HTTP client for arbitrary endpoints, and typed GIS-service clients composed over the same transport. Prefer one client/session abstraction and a response value with status, headers, bytes/text/JSON helpers, and explicit HTTP error handling; avoid overlapping public manager/session wrappers and mutable module-level singleton configuration.

UI-originated network requests should be asynchronous by default so they do not block QGIS's event loop; blocking use must be explicit and limited to suitable contexts. Define cancellation, timeout, and error semantics. Use fake/injected transports for tests rather than silently falling back to a separate production networking stack. For standard WMS/WFS layer loading, prefer QGIS providers/layer APIs; typed service clients are for custom protocol or REST operations. JavaScript bridge networking, if enabled, must be separately permissioned and return DTOs, not Qt reply objects.

ADR-4 remains proposed: requests-like direction and sync/async support are confirmed, subject to a Qt-compatible scheduling spike. Exact API shape and lifecycle details still require validation.

### Reference implementation notes

The `qgis-rust` repository was reviewed as a design reference, not as an API compatibility target. Useful ideas to adapt include requests-like convenience methods and response helpers, use of QGIS networking configuration, asynchronous content fetching, typed service clients, and layered runtime/bridge tests. Avoid reproducing its overlapping public `Session`/`NetworkManager`/`NetworkAccessManager` wrappers, blocking-by-default calls, and separate mutable manager configuration surfaces. Its CLI `dev` watch path is explicitly unimplemented, so it is not evidence of a working Live Server-style plugin workflow; this SDK's Desktop/standalone targets, QWebEngine HMR, and Python reload behavior need to be designed and implemented here. See the [reference network API](https://github.com/Archont561/qgis-rust/blob/main/py-packages/qgis-sdk/src/qgis_sdk/network.py), [network guide](https://github.com/Archont561/qgis-rust/blob/main/docs/src/content/docs/reference/network.mdx), and [CLI source](https://github.com/Archont561/qgis-rust/blob/main/py-packages/qgis-sdk/src/qgis_sdk/cli.py).

## 8. Build and distribution

- The developer installs the SDK/tooling in a Python environment; that environment is not itself the end-user plugin installation.
- `qgis-sdk build` validates metadata, imports/entry points, declared assets, and supported runtime requirements, then creates a ZIP whose root contains the plugin directory expected by QGIS.
- The archive contains the plugin's runtime source/modules, QGIS metadata, production UI assets, and other explicitly required resources. It excludes tests, development-only tooling, caches, and unbuilt frontend sources unless deliberately needed at runtime.
- For v1, bundle only the SDK runtime modules required by the plugin privately into its archive rather than requiring QGIS users to install a separate SDK runtime package. Keep the runtime modular inside the SDK distribution and revisit a standalone `qgis-sdk-runtime` distribution only if independent runtime stability, size, or release cadence warrants it.
- Validate the archive by inspecting its structure and, where practical, installing it into a clean QGIS profile/runtime.

The artifact split and private pure-Python-first bundling policy are accepted in ADR-3; implementation and clean-runtime verification remain outstanding.

## 9. Version-one scope and later direction

### Confirmed v1 direction

- Python plugin scaffold and metadata/lifecycle integration.
- Python declarative API and derived plugin description.
- Class-based Python Processing algorithms with execution-scoped context and typed inputs/results.
- Native Qt/QGIS usage and an optional WebEngine path for consumers; the release slice proves both paths, including vanilla TypeScript/React and dialog/dock containers. Schema-driven forms remain scoped by actual workflow needs.
- `dev` workflow for the applicable runtime context, with frontend HMR for web UI and a documented Python reload/restart behavior.
- Layered pytest support and QGIS-aware test fixtures.
- Minimal owned local jobs needed by the reference workflow; advanced orchestration is deferred.
- Generic QGIS-aware HTTP transport plus a small set of typed clients only as product scope confirms.
- Validated QGIS-installable ZIP build, distinct from SDK installation.

### Explicitly later/optional

Rust shipping, including SDK-owned acceleration and first-class author-written Rust tooling, is deferred beyond v1 and is not a v1 runtime dependency. If pursued, retain Python declarations and the Processing adapter, keep QGIS/Qt object handling in Python, use plain typed/batch inputs for native compute, and require benchmark evidence, parity tests, cancellation/progress semantics, and a platform/Python ABI packaging plan. See [decision-5](../../decisions/decision-5%20-%20Rust-algorithm-implementations-are-post-v1-and-backend-neutral.md).

## 10. Acceptance outcomes

The v1 direction is coherent when a developer can:

- scaffold a plugin and understand which generated files are required;
- declare plugin/UI structure in Python without hand-maintaining parallel JSON;
- run Python behavior in actual QGIS Desktop when `iface`/plugin lifecycle is needed, or use the explicitly narrower standalone Qt target;
- iterate on Python and optional web assets with a predictable dev loop;
- test pure logic without QGIS and opt into heavier Qt/QGIS/bridge layers;
- build a ZIP whose layout installs as a QGIS plugin and that does not require installing developer tooling on the target machine.

## 11. Open decisions

1. Final context/service contracts and public decorator/type API, plugin description schema versioning, and compatibility policy.
2. Which native declarative widgets/forms are part of v1 versus conventional PyQt code.
3. Exact Desktop reload mechanism and qualification; automatic safe reload is the intended default only after lifecycle tests pass.
4. Standalone runtime discovery/configuration and supported QGIS/Python matrix.
5. Exact async network API, authentication ownership, and which typed GIS services ship initially.
6. How private pure-Python-first bundling is implemented and licensed, including collision tests and unsupported-dependency diagnostics (policy accepted in ADR-3).
7. What constitutes a clean build/release gate for supported operating systems and QGIS versions.
8. Dataclass schema/validation backend (apischema vs Pydantic TypeAdapter or another proven implementation), coercion rules and runtime dependency/ABI costs.
9. Exact pure/native fixture names, collection isolation, context construction/factory contract and permitted runtime capabilities.
10. Endpoint injection syntax, event/error API, supported request/result types and the precise additive-compatibility algorithm (versioned compatibility direction accepted in ADR-18).


## 12. Responsibility boundaries and context

Proposed package responsibilities:

| Area | Owns | Must not depend on |
| --- | --- | --- |
| `models` | Dataclasses, values/IDs, descriptions, DTOs and diagnostics | QGIS/Qt, services, core, pytest, CLI |
| `services` | Small typed capability contracts (Protocols) | Concrete adapters, bridge transport, testing |
| `core` | Declarations/inspection, context composition, dispatch, lifecycle and owned resources | Native implementations, pytest, CLI |
| `adapters` | QGIS/Qt/Desktop/WebEngine implementations and explicit native escape hatch | Testing fakes |
| `bridge` | Explicit endpoints, transport-independent schema, authorization and dispatch | Unconditional native imports |
| `testing` | Fake services, harnesses and opt-in pytest fixtures | Unconditional QGIS/Qt imports |
| CLI/tooling | Checks, tests, dev orchestration, generation and packaging | Must not be imported by core |

Dependencies flow toward models and service contracts; adapters implement those contracts. This is an illustrative layout, not a commitment to create empty modules or a second GIS object model. Group by feature inside these boundaries as needed. Core may orchestrate models/services, but should not become a miscellaneous utility bucket.

Plugin authors use plain classes, optionally dataclasses with a typed `ctx` field. The runtime constructs them with a PluginContext or an explicit author factory. No mandatory Plugin base class, decorator constructor rewriting, hidden lifecycle injection or global registry. Declarations attach metadata only; a separate QGIS adapter implements classFactory/initGui/unload and deterministic cleanup.

Context exposes curated capabilities such as `layers`, `project`, `notify`, `settings`, `jobs`, `processing` and `network`. Start with real workflows instead of wrapping every PyQGIS method. Keep plugin-lifetime services separate from invocation-specific inputs, progress and cancellation. Native access is explicit and unavailable in pure mode/bridge DTOs. Specify thread affinity, layer invalidation, output ownership and CRS/units instead of hiding them behind convenience calls.

## 13. Fixture and testing design

Expose an opt-in pytest plugin with a function-scoped harness (illustratively `sdk_ctx`). Its `.ctx` is a production context backed by in-memory fakes; test-only helpers configure selections, settings, responses, scheduling and captured effects. Teardown checks/disposes owned resources and expectations; no automatic fake QGIS selected because a native runtime is missing.

Use separate native fixtures: a real headless QgsApplication, session-scoped per process, with isolated projects and explicit cleanup of global state. Do not create an application per test or shut down an externally owned app. Offscreen/virtual-display, Processing providers and WebEngine requirements are explicit. A headless app is not QGIS Desktop and supplies no real iface; test actual discovery/menu/lifecycle in Desktop with an isolated profile.

For SDK maintenance, combine example tests, Hypothesis properties/state machines and pytest-bdd workflows. Properties cover determinism, round-trips plus independent constraints, serializability, invalid inputs, safe paths and permission boundaries. State machines cover partial startup, repeated unload, cancellation, expired handles and late callbacks using controlled scheduling. Behavioral scenarios assert observable outcomes, not private call structure. Shared service contract tests compare fakes/native implementations only where their semantics overlap; fake Processing results do not prove geometry correctness. Run Python/TS bridge fixtures independently on both sides.

## 14. Declarative bridge and generated types

Offer a small FastAPI-inspired router with explicitly declared operations, typed dataclass requests/results and injected host dependencies excluded from the wire schema. Stable operation IDs are independent of method names. Query/command aliases and Context/Depends syntax are undecided. Registration is runtime-local; duplicate IDs fail and unmarked helpers stay private. This is RPC over QWebChannel, not HTTP; no HTTP server is required.

Generate DTOs, operation maps, thin typed clients, event payloads/subscriptions, validators and contract identity from one versioned description. Distinguish nullable/omittable/defaulted fields, define wire types and reject unsupported annotations rather than falling back to any. Evaluate apischema/JSON Schema-to-TS and Pydantic TypeAdapter without requiring author model inheritance; neither implementation is selected. TypeScript interfaces alone cannot enforce runtime constraints or type Promise rejections. A fingerprint is not a compatibility policy.

Use versioned envelopes, request correlation, named argument objects, separate success/error and event shapes, stable error codes and opaque session-scoped handles. Authorize host-side, deny by default even for empty permission sets, validate inputs/results, constrain origins/navigation and never expose raw native objects/secrets/arbitrary invocation. Share one QWebChannel per transport; define readiness, failures/timeouts, reconnection and disposal. Page reload needs bridge reattachment/state synchronization; plugin reload also replaces handlers and invalidates old references. JS Promises do not make Python slots non-blocking; scheduling/GUI-thread handoff is an explicit unresolved design.

## 15. Build/dev refinements and reference lessons

Development owns its watcher/frontend processes and isolated profile, unloads resources before controlled Python reload, and reports restart-only changes. Frontend HMR is separate from Python reload. Failed reload leaves an explicit disabled state rather than promising safe rollback. Production assets never depend on the dev server; remote debugging is opt-in.

Build uses staging and shared source checks, validates generated artifacts and ZIP paths/layout, excludes secrets/tests/caches/dev tooling, includes licenses and uses plugin-private bundled runtime imports to avoid cross-plugin version collisions. Third-party dependency/ABI policy is explicit; never install packages silently at plugin startup. Packaging success is not functional verification; CI composes checks, generation consistency, appropriate tests and artifact verification separately.

Reference review: Archont561/qgis-rust at commit `ba03fa042e2e2f3dad79b492d8957316e7a9a52c` (source inspection only). Adapt domain namespaces, generated descriptions, shared channel ownership and cross-language vectors. Avoid decorator constructor/lifecycle rewriting, global registration, automatic public-callable exposure, empty-permission grant-all behavior, implicit native-to-fake fallback and assumptions that the written testing protocol is fully implemented by every runtime path. Do not introduce that repository's Rust engine architecture into this SDK.

## 16. Related design decisions

- [decision-6](../../decisions/decision-6%20-%20Separate-models-services-core-and-runtime-adapters.md)
- [decision-7](../../decisions/decision-7%20-%20Use-layered-pytest-fixtures-properties-and-behavioural-contracts.md)
- [decision-8](../../decisions/decision-8%20-%20Separate-check-test-dev-and-build-workflows.md)
- [decision-9](../../decisions/decision-9%20-%20Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md)
- [decision-10](../../decisions/decision-10%20-%20Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md)


## 17. Scoped class-based authoring and refresh refinements

The preferred algorithm shape supersedes the earlier grouped-method sketch: one decorated plain class per algorithm with one typed run(inputs) entry point and fresh constructor-injected self.ctx: AlgorithmContext per execution. A provider groups declarations; the native adapter owns Processing parameter/output conversion and thread-affine phases. Dialogs/docks likewise use one controller class per meaningful surface, a lazy build() factory and a view-scoped UiContext. Actions normally remain methods. PluginContext, AlgorithmContext, UiContext and JobContext share selected service contracts, not one unrestricted universal context.

Jobs use typed class declarations and Celery-inspired delay/handle/retry ergonomics bound through the owning runtime, not a global task registry. Execution remains local initially; cancellation acknowledgment, idempotent retries, GUI-thread completion and deterministic ownership are explicit. Distributed workers, persistent schedules and chains are not implied capabilities.

Networking uses requests-like vocabulary with QGIS-aware auth/proxy behavior, scoped cancellation, response values and safe scheduling. Styling separates reusable GIS layer presentation from UI themes; packaged QML/native theme inheritance are the initial direction. Check rejects inappropriate eager QGIS imports and pure-to-native dependencies, with narrow native and TYPE_CHECKING exceptions, complemented by import-boundary tests.

Development distinguishes frontend HMR, controlled Python runtime replacement and restart-required changes. Preflight failures retain the prior revision; post-teardown startup failures disable the plugin with diagnostics. Serialize reloads, wait for safe owned-work termination, invalidate old generations and restore only explicitly serializable presentation state. Exact public APIs, scheduler, refresh transport and schema backend remain open.

Additional proposed ADRs:

- [decision-11](../../decisions/decision-11%20-%20Use-one-context-injected-class-per-Processing-algorithm.md)
- [decision-12](../../decisions/decision-12%20-%20Use-one-context-injected-controller-per-UI-surface.md)
- [decision-13](../../decisions/decision-13%20-%20Use-runtime-bound-Celery-inspired-local-jobs.md)
- [decision-14](../../decisions/decision-14%20-%20Enforce-QGIS-free-import-boundaries-during-check.md)
- [decision-15](../../decisions/decision-15%20-%20Refresh-development-through-owned-runtime-generations.md)
- [decision-16](../../decisions/decision-16%20-%20Separate-reusable-layer-styles-from-UI-themes.md)


## 18. Confirmed release and frontend decisions (2026-10-16)

The clarification interview selected one complete vertical slice rather than every capability at once. Prove plain Python authoring, native and web views, typed clients, testing, CLI and minimal local jobs through a working reference plugin. Broad service namespaces are not a promise to wrap all of QGIS or ship advanced job orchestration.

Target QGIS 4 on Windows/Linux x86-64 through an explicit tested matrix. The development QGIS 4.2.3 pin is a qualification starting point, not support evidence for either platform or all 4.x. Defer QGIS 3, macOS and Rust shipping. Preserve implementation-neutral compute contracts only where real workflows justify them.

Ship a framework-neutral bridge with vanilla TypeScript and React adapters/templates, both dialogs and docks, Vite for apps, npm/pnpm/Bun selection and Vitest for generated frontend tests. Bunup remains a library tool, not a package-manager-triggered replacement for Vite. Expose broad curated host capabilities under deny-by-default, host-enforced per-view allowlists. Use versioned compatibility with explicitly defined additive changes; fingerprints diagnose drift, not compatibility.

Choose the dataclass schema/validation backend only after a compatibility spike. Support GUI-safe synchronous handlers and non-blocking/coroutine operations subject to a successful Qt scheduler spike on target runtimes. Bundle runtime dependencies privately under a pure-Python-first policy; mandatory native validators require an explicit policy revisit. new installs dependencies only after explicit opt-in. Automatic Python reload becomes the default only after safe lifecycle behavior is tested.

See [decision-17](../../decisions/decision-17%20-%20Deliver-a-qualified-Python-first-vertical-slice-for-v1.md) and [decision-18](../../decisions/decision-18%20-%20Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md). Detailed bridge, testing and questionnaire design: [doc-2](doc-2%20-%20Web-bridge-and-scaffolding-design.md).


## 19. Confirmed behavior and safety decisions (second interview)

The reference slice is local vector input, selection inspection, one Processing operation and styled output, with equivalent native/web behavior. Preserve sources; finalize new temporary outputs and add them to the project only on success. Use explicit projected working CRS/units for distance operations and explicit transformation choices, never silently interpret degrees as metres. Permanent exports need destination/overwrite authority and partial-file cleanup.

View-owned jobs request cancellation and detach UI callbacks on disposal; hiding docks does not dispose them. Plugin-lifetime work is explicit. Initial jobs do not retry automatically. If safe completion is not reached within the bounded reload policy, refuse in-process replacement and require explicit restart.

Bridge resources use opaque scoped handles that fail when stale/foreign. File access requires picker/plugin grants, not arbitrary frontend paths. Restrict host URL/method/auth/redirect authority and separately enforce browser navigation/resource restrictions. Strict requests reject unknown fields/implicit coercion; result readers validate known fields and permit only explicitly compatible additions. Expected failures use typed errors; unexpected failures expose safe correlation IDs while detailed diagnostics stay on the host.

Generated TS bindings are checked in with deterministic generation and CI drift checks. Initial public releases are experimental 0.x rather than an immediate stable-1.0 promise. Failed async qualification triggers an explicit scope decision with the user. Mechanisms, exact schemas/names, numeric limits and native evidence remain open.

Detailed scenarios: [doc-3](doc-3%20-%20Reference-workflow-and-runtime-safety-acceptance.md). Related accepted decisions: [decision-19](../../decisions/decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md), [decision-20](../../decisions/decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md), [decision-21](../../decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md), [decision-22](../../decisions/decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md).


## 20. Proposed Tauri-inspired bridge refinement

A source review proposes a small invocation kernel beneath generated typed clients, one host dispatcher with trusted caller identity, distinct invocation/event/stream contracts, ownership-aware explicit resource release, injected transport mocks and cancellation acknowledgement separate from Promise abort. No Tauri dependency, Rust shipping or binary-transport guarantee is introduced. See [decision-23](../../decisions/decision-23%20-%20Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md) and the web bridge specification, section 10. These are proposed implementation refinements; previously accepted policies are unchanged.


## 21. Versioned implementation roadmap

Targets 0.1.0–0.5.0 cover the initial experimental slice, each with an explicit dependency-backed release task. 0.6.0 is a tentative deferred research target, not Rust shipping. Targets do not bump manifests or promise stable 1.0.0. See [doc-4](../plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md) for the task inventory, evidence rules and SemVer policy.
