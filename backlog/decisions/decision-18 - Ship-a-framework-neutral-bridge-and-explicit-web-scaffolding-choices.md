---
id: decision-18
title: Ship a framework neutral bridge and explicit web scaffolding choices
date: '2026-10-16 08:37'
status: accepted
---
## Context

The user confirmed the TypeScript/frontend direction, authorization policy and scaffold choices in the 2026-10-16 clarification interview. Previously, these details existed only in conversation. The package currently contains a smoke-test scaffold.

## Decision

Keep one framework-neutral bridge runtime with isolated protocol/transport/client/host-capability responsibilities. Offer vanilla TypeScript and a thin React adapter initially; defer Vue/Svelte support. Root imports must not load React, test utilities, a browser connection or native globals eagerly. Adapter entry points are optional; exact exports are provisional. Generate plugin-specific DTOs, operation maps, callable clients, events and validators from Python rather than duplicate handwritten contracts. Share lifecycle/correlation/reconnection plumbing in the runtime.

Expose the broad host API direction: layers, project, notifications, settings, Processing, jobs and networking, alongside plugin-declared operations. Enforce per-view allowlists on the Python host, deny by default, with read/write and operation/resource constraints where relevant. Do not substitute empty success for permission denial or host unavailability. The exact operation inventory is still to be specified; broad namespaces do not authorize arbitrary native objects, file paths, destinations or algorithms.

Use versioned compatibility rules: reject incompatible protocol/schema changes and permit explicitly defined compatible additive changes. A contract fingerprint diagnoses drift but does not alone decide compatibility. Precisely define additive compatibility, unknown-field behavior and negotiation tests before implementation.

Use Vite for generated web applications with a questionnaire choice of npm, pnpm or Bun. Bunup remains appropriate for reusable library/component-library scaffolds, not an automatic Vite replacement when Bun is selected. Use Vitest for generated vanilla/React tests across package managers. The repository bridge library may continue its existing Bunup/Bun test workflow; this decision does not silently migrate its tooling.

new supports both dialog and dock scaffolds. Interactive answers and non-interactive flags feed the same validated options and generation plan. Downloads/installations are explicit opt-in (interactive consent or --install); never provision QGIS/system toolchains implicitly. Validate combinations, refuse unintended overwrites and preserve generated files with a retry command when optional installation fails. Template versions are controlled and generated browser targets must match qualified QGIS Chromium capabilities.

## Consequences

- Provide typed client/host fakes, deterministic transport/events/faults and leak assertions; keep real QWebEngine tests separate from browser mock tests.
- Generated projects include a framework-neutral bootstrap, generated bindings, native/backend integration and small component/contract examples.
- Questionnaire implementation/library, exact template tree, export names, scaffold flags and compatibility details remain engineering choices.

## Confirmed second-interview refinement (2026-10-16)

[decision-20](decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md) refines resource/network/browser authority and handles; [decision-22](decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md) refines validation, errors, compatibility and generated-file ownership.
