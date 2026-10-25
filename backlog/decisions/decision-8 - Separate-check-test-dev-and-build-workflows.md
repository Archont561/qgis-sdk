---
id: decision-8
title: Separate check test dev and build workflows
date: '2026-10-16 07:43'
status: proposed
---
## Context

Validation, behavior tests, interactive development and artifact construction have different effects and runtime requirements. One command should not silently perform all four.

## Decision

Proposed command responsibilities:

- `qgis-sdk check`: non-mutating source/configuration/declaration/asset/dependency-policy checks without QGIS by default. No installs, frontend build, source rewrites or implicit test run. Support actionable stable diagnostics and eventually machine-readable output/warnings-as-errors. Declaration imports may execute author top-level code; isolated inspection is not a security sandbox.
- `qgis-sdk test`: a thin environment-aware pytest runner. Default to pure tests, explicitly select QGIS or Desktop targets, forward pytest arguments after `--`, preserve output/exit status, isolate temporary resources and clean up. Runtime selection and collection policy must not import native-only modules in pure mode. No implicit dependency downloads or silent all-skipped success for a required gate.
- `qgis-sdk dev`: default to real QGIS Desktop using explicit configuration/runtime discovery and an isolated profile. Stage source plugin/adapters, load it through real lifecycle and watch sources. Reload by unloading owned resources, cancelling work, replacing plugin-owned modules and recreating handlers/views. Unsafe changes require restart; failed reload leaves an explicitly disabled plugin rather than pretending rollback always works. Start a frontend server only for web UI, bound to loopback by default, with bridge-origin restrictions and frontend HMR. Standalone and fake preview targets are explicit, reduced-capability options, not equivalent to Desktop.
- `qgis-sdk build`: rerun shared source checks, generate adapters, build optional production frontend assets, stage runtime/resources, validate archive contents and create a QGIS-installable ZIP. Do not implicitly run the behavior suite or install/publish into the user's profile. Optional requested real-QGIS verification fails clearly if unavailable; packaging success alone is not proof of startup correctness.

Build calls shared checking APIs, not the check CLI subprocess; a previous check cannot replace validation of current source/generated output. API generation produces deterministic files and supports stale-output checking; exact command spelling and flags remain provisional. CI composes checks, appropriate test gates, generation checks and build explicitly.

## Consequences

- Exact targets/flags are illustrative until CLI implementation, but their runtime and side-effect boundaries are fixed design goals.
- Development context discovery is not tied exclusively to this repository's Pixi-pinned QGIS.
- The CLI does not replace pytest or the frontend build tool; it orchestrates them with clear evidence and cleanup.

## Related checking and refresh refinements

Import-boundary rules and native runtime resolution are detailed in [decision-14](decision-14%20-%20Enforce-QGIS-free-import-boundaries-during-check.md). Development preflight, safe teardown, generation invalidation and restart policy are detailed in [decision-15](decision-15%20-%20Refresh-development-through-owned-runtime-generations.md).

## Confirmed development and scaffold policy (2026-10-16)

Automatic Python reload is the intended default only after lifecycle tests prove safe teardown and reconstruction (ADR-15). Unsafe changes require restart. Scaffolding downloads dependencies only after explicit consent; non-interactive installation requires an explicit option. The accepted release boundary is ADR-17 and web scaffolding choices are ADR-18. Exact CLI flags remain illustrative.

## Implemented shape of `test` and `dev` (2026-10-25)

TASK-26 and TASK-6 fixed the command spelling that was illustrative above:
`qgis-sdk test [PYTEST_ARGS]... [--project PATH] [--target pure|qgis|desktop|web]
[--qgis-prefix PATH]` and `qgis-sdk dev [PATH] [--mode desktop|standalone]
[--qgis-prefix PATH] [--no-web] [--port N]`. Both commands plan a process
(`qgis_sdk.devtools.plan_tests` / `plan_dev`) and run it through the CLI
runtime (decision-34), so the plans are unit-tested and the binary is driven
by one opt-in harness. The pure target is also an import guard: a test that
imports a native module fails rather than passing by accident, and a native
target whose selection only skipped fails the gate. `dev` loads the source
plugin through `QGIS_PLUGINPATH` and a project-local profile
(`.qgis-sdk/profiles/dev`), reloads on demand (preflight compile, refuse on
syntax errors, leave disabled on a failed unload/start) and starts a Vite
dev server on loopback only for a project with a web UI, handing its origin
to the QGIS process as `QGIS_SDK_DEV_SERVER`; the generated view honours the
variable, a build never does. Source watching with automatic Python reload
stays behind decision-15 and TASK-21.
