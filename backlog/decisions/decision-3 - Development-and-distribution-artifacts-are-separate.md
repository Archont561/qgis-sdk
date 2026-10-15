---
id: decision-3
title: Development and distribution artifacts are separate
date: '2026-10-15 23:05'
status: proposed
---
## Context

Plugin authors need the SDK's CLI, scaffolding, dev server, test helpers, and build tooling. QGIS users installing a plugin need its plugin code and runtime, not the SDK's development toolchain. A plugin ZIP also has a different installation target and layout from a Python package installed into a development environment. The reviewed `qgis-rust` CLI's `build` command delegates to `package`, which creates a ZIP with the plugin directory as its root; that artifact distinction is useful, but it does not settle this repository's runtime-bundling policy.

## Decision

Proposed: distribute `qgis-sdk` as developer tooling, and make `qgis-sdk build` produce a QGIS-installable ZIP with the plugin directory at the ZIP root, required runtime modules, metadata, and production assets. Exclude tests, dev tools, and unbuilt development assets. Bundle only the SDK runtime modules needed by that plugin. Do not create a separate `qgis-sdk-runtime` distribution for v1; revisit that split only if the runtime becomes a stable independent product or its size/release cadence materially warrants separate distribution.

## Consequences

- Build output needs a verifiable installable layout and a clear runtime dependency/bundling policy.
- SDK installation and plugin installation must be documented and tested as different workflows.
- Bundling runtime code can duplicate files across plugins; a shared runtime installed by users is not assumed.
- This remains proposed pending explicit confirmation of the distribution policy and licensing/update implications.