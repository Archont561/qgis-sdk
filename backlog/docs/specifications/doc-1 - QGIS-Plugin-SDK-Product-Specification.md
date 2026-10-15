---
id: doc-1
title: QGIS Plugin SDK Product Specification
type: specification
created_date: '2026-10-15 23:04'
---

# QGIS Plugin SDK Product Specification

**Status:** Working specification based on design discussion; the proposed ADRs remain open for confirmation. This document describes intended product behavior, not an implementation plan or a promise that every feature ships in v1.

## 1. Purpose and users

Provide a Python-first SDK and toolchain for authoring, developing, testing, building, and distributing QGIS plugins. The primary user is a Python developer who wants a repeatable plugin structure, a declarative UI layer where useful, a fast development loop, and installable QGIS output without hand-assembling runtime files.

The SDK should support both conventional QGIS plugins and plugins that use a web UI, without requiring every plugin to use QWebEngine or TypeScript.

## 2. Product principles

1. **Python owns plugin behavior.** Decorators and typed declarations describe plugin/UI structure; normal Python methods implement behavior. See [decision-1](../../decisions/decision-1%20-%20Python-declarative-API-is-the-plugin-authoring-source.md).
2. **One derived description contract.** Tooling and UI renderers consume an inspectable description derived from Python. JSON is generated/interchange, not independently authored truth. See [decision-2](../../decisions/decision-2%20-%20The-plugin-description-is-the-shared-schema-contract.md).
3. **QGIS is the runtime authority.** Prefer a QGIS executable available on `PATH` or a QGIS/PyQGIS installation importable by the selected Python environment. Do not require the SDK workspace's Pixi-pinned QGIS runtime as the only supported runtime.
4. **Differentiate runtime contexts.** A pure PyQt application, even one that initializes PyQGIS and embeds `QgsMapCanvas`, is not equivalent to a QGIS Desktop plugin. Features requiring `iface`, plugin discovery, or the plugin lifecycle must run in QGIS Desktop.
5. **Keep authoring and installation artifacts distinct.** `pip install qgis-sdk` is for developers; the build output is a QGIS-installable plugin archive. A separate runtime distribution is not planned for v1 under the proposed policy.
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

1. `qgis-sdk new plugin <name>` creates a minimal plugin package with metadata, a Python entry point, tests, and optional UI assets.
2. `qgis-sdk new algorithm <name>` adds a Python Processing algorithm scaffold.
3. `qgis-sdk new ui <name>` adds a native or web UI scaffold using the same Python description API.
4. `qgis-sdk dev` launches the selected runtime with the working plugin loaded and watches relevant sources.
5. The author runs the generated test commands and adds tests appropriate to each runtime layer.
6. `qgis-sdk build` validates and creates a QGIS-installable ZIP.

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

Provide injectable fakes for external services and QGIS-dependent collaborators. Use `pytest-bdd` where behavior benefits from readable scenario specifications, while retaining ordinary pytest tests for lower-level cases. Avoid making all tests depend on a full Desktop install. The current repository has `pytest-bdd==9.0.0` declared in the SDK dev extra and root Pixi PyPI dependencies; the lockfile still needs a separate relock/consistency check.

## 7. Networking and GIS services

The intended API has one shared injectable transport that respects QGIS networking configuration (proxy, authentication, and certificates), a generic HTTP client for arbitrary endpoints, and typed GIS-service clients composed over the same transport. Prefer one client/session abstraction and a response value with status, headers, bytes/text/JSON helpers, and explicit HTTP error handling; avoid overlapping public manager/session wrappers and mutable module-level singleton configuration.

UI-originated network requests should be asynchronous by default so they do not block QGIS's event loop; blocking use must be explicit and limited to suitable contexts. Define cancellation, timeout, and error semantics. Use fake/injected transports for tests rather than silently falling back to a separate production networking stack. For standard WMS/WFS layer loading, prefer QGIS providers/layer APIs; typed service clients are for custom protocol or REST operations. JavaScript bridge networking, if enabled, must be separately permissioned and return DTOs, not Qt reply objects.

This direction is recorded as a proposed ADR; API shape and lifecycle details still need confirmation.

### Reference implementation notes

The `qgis-rust` repository was reviewed as a design reference, not as an API compatibility target. Useful ideas to adapt include requests-like convenience methods and response helpers, use of QGIS networking configuration, asynchronous content fetching, typed service clients, and layered runtime/bridge tests. Avoid reproducing its overlapping public `Session`/`NetworkManager`/`NetworkAccessManager` wrappers, blocking-by-default calls, and separate mutable manager configuration surfaces. Its CLI `dev` watch path is explicitly unimplemented, so it is not evidence of a working Live Server-style plugin workflow; this SDK's Desktop/standalone targets, QWebEngine HMR, and Python reload behavior need to be designed and implemented here. See the [reference network API](https://github.com/Archont561/qgis-rust/blob/main/py-packages/qgis-sdk/src/qgis_sdk/network.py), [network guide](https://github.com/Archont561/qgis-rust/blob/main/docs/src/content/docs/reference/network.mdx), and [CLI source](https://github.com/Archont561/qgis-rust/blob/main/py-packages/qgis-sdk/src/qgis_sdk/cli.py).

## 8. Build and distribution

- The developer installs the SDK/tooling in a Python environment; that environment is not itself the end-user plugin installation.
- `qgis-sdk build` validates metadata, imports/entry points, declared assets, and supported runtime requirements, then creates a ZIP whose root contains the plugin directory expected by QGIS.
- The archive contains the plugin's runtime source/modules, QGIS metadata, production UI assets, and other explicitly required resources. It excludes tests, development-only tooling, caches, and unbuilt frontend sources unless deliberately needed at runtime.
- For v1, prefer bundling only the SDK runtime modules required by the plugin into its archive rather than requiring QGIS users to install a separate SDK runtime package. Keep the runtime modular inside the SDK distribution and revisit a standalone `qgis-sdk-runtime` distribution only if independent runtime stability, size, or release cadence warrants it.
- Validate the archive by inspecting its structure and, where practical, installing it into a clean QGIS profile/runtime.

The artifact split is a proposed decision, not yet user-confirmed.

## 9. Version-one scope and later direction

### Candidate v1 scope

- Python plugin scaffold and metadata/lifecycle integration.
- Python declarative API and derived plugin description.
- Native Qt/QGIS usage, with optional schema-driven forms and optional WebEngine/TypeScript bridge.
- `dev` workflow for the applicable runtime context, with frontend HMR for web UI and a documented Python reload/restart behavior.
- Layered pytest support and QGIS-aware test fixtures.
- Generic QGIS-aware HTTP transport plus a small set of typed clients only as product scope confirms.
- Validated QGIS-installable ZIP build, distinct from SDK installation.

### Explicitly later/optional

Rust-backed algorithm execution is post-v1 and is not a v1 runtime dependency. If pursued, retain Python declarations and the Processing adapter, keep QGIS/Qt object handling in Python, use plain typed/batch inputs for native compute, and require benchmark evidence, parity tests, cancellation/progress semantics, and a platform/Python ABI packaging plan. See [decision-5](../../decisions/decision-5%20-%20Rust-algorithm-implementations-are-post-v1-and-backend-neutral.md).

## 10. Acceptance outcomes

The v1 direction is coherent when a developer can:

- scaffold a plugin and understand which generated files are required;
- declare plugin/UI structure in Python without hand-maintaining parallel JSON;
- run Python behavior in actual QGIS Desktop when `iface`/plugin lifecycle is needed, or use the explicitly narrower standalone Qt target;
- iterate on Python and optional web assets with a predictable dev loop;
- test pure logic without QGIS and opt into heavier Qt/QGIS/bridge layers;
- build a ZIP whose layout installs as a QGIS plugin and that does not require installing developer tooling on the target machine.

## 11. Open decisions

1. Final public decorator/type API, plugin description schema versioning, and compatibility policy.
2. Which native declarative widgets/forms are part of v1 versus conventional PyQt code.
3. Exact Desktop reload mechanism and when restart is required.
4. Standalone runtime discovery/configuration and supported QGIS/Python matrix.
5. Exact async network API, authentication ownership, and which typed GIS services ship initially.
6. Whether the proposed bundled-runtime/plugin-ZIP policy is accepted and what license notices it requires.
7. What constitutes a clean build/release gate for supported operating systems and QGIS versions.
