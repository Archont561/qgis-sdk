---
id: decision-3
title: Development and distribution artifacts are separate
date: '2026-10-15 23:05'
status: accepted
---
## Context

The developer SDK and the QGIS-installed plugin have different consumers and runtime needs. The user explicitly confirmed plugin-private bundling and a pure-Python-first dependency policy on 2026-10-16. This replaces the earlier provisional distribution wording; it does not prove packaging is implemented.

## Decision

Distribute qgis-sdk as developer tooling. qgis-sdk build produces a QGIS-installable ZIP with one plugin root, required plugin-private SDK runtime modules, metadata, declared resources and production web assets. End users install the plugin ZIP without separately installing the SDK runtime or developer tooling. Do not create a separate required shared qgis-sdk-runtime installation for v1.

Bundle reviewed pure-Python runtime dependencies first. Reject unsupported/undeclared dependencies and incompatible native artifacts with actionable diagnostics; do not claim general native-wheel vendoring. Never install dependencies at plugin startup. If the validation spike selects a mandatory native dependency, explicitly revisit this policy before acceptance rather than silently violating it.

Build reruns shared source checks, generates adapters/assets in staging and validates paths/layout/runtime contents. Exclude QGIS/Qt, tests/fixtures, CLI, environments, caches, secrets and unbuilt development assets. Include licenses/notices. Plugin-private imports and a two-plugin different-SDK-version test must guard collisions. Prefer explicit runtime components over speculative Python tree shaking and aim for deterministic artifacts.

Do not implicitly run the behavior suite, publish or install into a user's profile. Requested real-QGIS installation/startup verification is separate and must fail clearly if its required runtime is unavailable. A valid ZIP alone is not proof of behavior.

## Consequences

- Qualification must use clean target environments and include dependency/license checks.
- Pure-Python-first packaging and deferred Rust reduce initial native distribution scope, not the need to test host-provided QGIS/Qt compatibility.
- Binary dependencies, separate runtime products and multi-platform native ZIP strategies require a later explicit decision.
