---
id: doc-4
title: SemVer delivery roadmap and task dependencies
type: guide
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:03'
---
# SemVer delivery roadmap and task dependencies

**Status:** Planning targets only. All implementation and release tasks remain To Do. No package versions are bumped, no implementation is claimed, and no deadlines are invented.

## Version policy

Milestones use valid major.minor.patch targets. Experimental 0.x breaking changes get a documented minor release; patches are compatible fixes. Use prereleases such as 0.3.0-alpha.1/0.3.0-beta.1. Stable 1.0.0 requires a later explicit API-stability decision.

`qgis-sdk` and `@archont561/qgis-sdk-bridge` **version independently** ([decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)). Each package derives its own version from the conventional commits that touch it, starting from its own last release tag; `python-v*` stamps `pyproject.toml` and `recipe.yaml`, `ts-v*` stamps the bridge `package.json`, and `v*` is a deliberate alignment release that stamps all three. What holds a pair together is the plugin-description **contract version** (`PLUGIN_DESCRIPTION_SCHEMA_VERSION`), declared once per language and checked by `release.py verify-versions` on every release; wire protocol versions stay independent of package versions. Within a milestone, feature and fix work bumps only the patch; the minor advances on a breaking change or when a milestone closes by an explicit `--bump minor`/`--version-override`, **per package**. Existing unreleased 0.1.0 metadata is not proof of a published usable release. The 0.6.0 reservation is tentative deferred research and requires renewed approval, not a Rust-shipping commitment.

## Milestones and release tasks

| Milestone | Python version (`qgis-sdk`) | Python deliverable | Bridge version (`@archont561/qgis-sdk-bridge`) | Bridge deliverable | Release gate |
| --- | --- | --- | --- | --- | --- |
| 0.1.0 [m-0](../../milestones/m-0%20-%200.1.0-%E2%80%94-architecture-and-qualification-spikes.md) | 0.1.0 → 0.1.1, published | Contracts, declarations, scheduler spikes | 0.1.0 → 0.1.1, published | Wire primitives: description parsing, safe integers, error hierarchy | [TASK-27](../../tasks/task-27%20-%20Prepare-and-qualify-0.1.0-release.md) |
| 0.2.0 [m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md) | **0.2.0** | Native runtime, Processing algorithms, UI dispatch, HTTP, jobs | **stays at 0.1.1 — not released** | No source change; no npm version consumed | [TASK-28](../../tasks/task-28%20-%20Prepare-and-qualify-0.2.0-release.md) |
| 0.3.0 [m-2](../../milestones/m-2%20-%200.3.0-%E2%80%94-typed-bridge-and-web-ui.md) | **0.3.0** | Transport host side, per-view authority, generated fixtures | **0.2.0** | Transport contract, generated clients, React helpers, resource authority | [TASK-29](../../tasks/task-29%20-%20Prepare-and-qualify-0.3.0-release.md) |
| 0.4.0 [m-3](../../milestones/m-3%20-%200.4.0-%E2%80%94-developer-workflow-and-plugin-packaging.md) | **0.4.0** | Scaffolds, check/test/dev/build, ZIP packaging | **unchanged (0.2.x)** | New consumers (generated projects), not new surface | [TASK-30](../../tasks/task-30%20-%20Prepare-and-qualify-0.4.0-release.md) |
| 0.5.0 [m-4](../../milestones/m-4%20-%200.5.0-%E2%80%94-qualified-experimental-reference-release.md) | **0.5.0** | Qualified reference workflow and compatibility gates | **unchanged unless a defect is found** | Qualified as a pair through a real WebEngine view | [TASK-31](../../tasks/task-31%20-%20Prepare-and-qualify-0.5.0-release.md) |
| 0.6.0 [m-5](../../milestones/m-5%20-%200.6.0-%E2%80%94-deferred-native-compute-feasibility-%28tenta.md) | tentative | Deferred research only | no release | None planned; nothing published unless revived | [TASK-32](../../tasks/task-32%20-%20Prepare-and-qualify-0.6.0-release-tentative-deferred-target.md) |

## Bridge across milestones

The two artifacts are published independently, so each milestone states a version for each one under its **Bridge track** heading. There are three states:

- **Released with its own version** — 0.3.0 ([m-2](../../milestones/m-2%20-%200.3.0-%E2%80%94-typed-bridge-and-web-ui.md)) is the only milestone that changes bridge source, and it releases the bridge at **0.2.0** (a minor set explicitly at the close) while Python ships 0.3.0. The numbers differ because the histories differ, which is the point of [decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md).
- **Not released** — 0.2.0 ([m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md)) touches no bridge source, so it publishes no bridge version at all and `package.json` keeps 0.1.1. No npm version is consumed.
- **Released only for a fix** — 0.4.0 ([m-3](../../milestones/m-3%20-%200.4.0-%E2%80%94-developer-workflow-and-plugin-packaging.md)) adds consumers but not surface, and 0.5.0 ([m-4](../../milestones/m-4%20-%200.5.0-%E2%80%94-qualified-experimental-reference-release.md)) adds qualification. A bridge release in either one is a patch that exists because something broke.

What holds a pair together is the contract version, not a shared number. `release.py verify-versions` checks `PLUGIN_DESCRIPTION_SCHEMA_VERSION` across the Python declarations and the bridge index on every release, in every scope, and it refuses a workspace where the two disagree. A change to a serialized shape is therefore either additive (no contract bump) or bumps the contract in the change set that ships both packages. `v*` remains available as a deliberate alignment release when re-coupling the numbers is the clearest statement; it is not the default.

## Execution and evidence

Spikes/contracts precede declarations and runtime construction; scaffolding depends on the core, not the reverse. Native services/algorithms/jobs precede host dispatch. Generated bindings precede framework templates. Each release task depends on its milestone implementation and the preceding release gate. Deferred native research depends on the qualified initial slice and renewed approval.

Every implementation task includes focused tests; fixture integration is not permission to postpone them. Pure tests do not prove native/GUI/geometry/security behavior. Record inaccessible target environments and failed scheduler/validator criteria as blockers, then revisit scope explicitly. Preserve source data, ownership, safe cancellation, experimental API/migration policy and per-view authorization throughout.

## Task inventory

### 0.1.0

- [TASK-2](../../tasks/task-2%20-%20Implement-Python-declarations-and-generated-plugin-description.md): Implement Python declarations and generated plugin description
- [TASK-11](../../tasks/task-11%20-%20Establish-QGIS-free-models-services-and-context-contracts.md): Establish QGIS free models services and context contracts
- [TASK-12](../../tasks/task-12%20-%20Evaluate-dataclass-validation-and-TypeScript-generation-backends.md): Evaluate dataclass validation and TypeScript generation backends
- [TASK-13](../../tasks/task-13%20-%20Prove-Qt-compatible-coroutine-scheduling-and-safe-cancellation.md): Prove Qt compatible coroutine scheduling and safe cancellation
- [TASK-23](../../tasks/task-23%20-%20Qualify-candidate-QGIS-4-Windows-and-Linux-toolchains.md): Qualify candidate QGIS 4 Windows and Linux toolchains
- [TASK-27](../../tasks/task-27%20-%20Prepare-and-qualify-0.1.0-release.md): Prepare and qualify 0.1.0 release

### 0.2.0

No task in this milestone changes `packages/qgis-sdk-bridge`, so the 0.2.0 release publishes only the Python package and the bridge stays at 0.1.1 (see [m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md)).

- [TASK-1](../../tasks/task-1%20-%20Scaffold-a-QGIS-plugin-project-from-the-CLI.md): Scaffold a QGIS plugin project from the CLI
- [TASK-3](../../tasks/task-3%20-%20Render-schema-driven-native-UI-and-dispatch-Python-handlers.md): Render schema-driven native UI and dispatch Python handlers
- [TASK-5](../../tasks/task-5%20-%20Add-a-QGIS-aware-HTTP-client-and-typed-GIS-service-layer.md): Add a QGIS-aware HTTP client and typed GIS-service layer
- [TASK-14](../../tasks/task-14%20-%20Implement-class-based-Processing-algorithms-and-safe-outputs.md): Implement class based Processing algorithms and safe outputs
- [TASK-15](../../tasks/task-15%20-%20Implement-scoped-local-jobs-and-typed-result-handles.md): Implement scoped local jobs and typed result handles
- [TASK-24](../../tasks/task-24%20-%20Implement-scoped-plugin-runtime-and-native-lifecycle-adapter.md): Implement scoped plugin runtime and native lifecycle adapter
- [TASK-25](../../tasks/task-25%20-%20Implement-curated-native-services-and-packaged-style-support.md): Implement curated native services and packaged style support
- [TASK-28](../../tasks/task-28%20-%20Prepare-and-qualify-0.2.0-release.md): Prepare and qualify 0.2.0 release
- [TASK-38](../../tasks/task-38%20-%20Epic-v2-0.2.0-native-runtime-and-Processing-algorithms.md): Epic for this milestone. A tracking container only, with no scope of its own; the sprint order it encodes is in [doc-9](doc-9%20-%20V2-sprint-train-and-0.2.0-dependency-order.md).

### 0.3.0

The only milestone that changes bridge source, and the only one that releases the bridge on its own version (0.2.0). The remaining tasks are the Python-side contract and fixture work they depend on.

- [TASK-4](../../tasks/task-4%20-%20Add-the-versioned-WebEngine-bridge-contract.md): Add the versioned WebEngine bridge contract — **bridge source**
- [TASK-7](../../tasks/task-7%20-%20Add-layered-pytest-support-and-BDD-fixtures.md): Add layered pytest support and BDD fixtures
- [TASK-17](../../tasks/task-17%20-%20Generate-checked-in-TypeScript-contracts-clients-and-validators.md): Generate checked in TypeScript contracts clients and validators — **bridge source**
- [TASK-18](../../tasks/task-18%20-%20Add-thin-React-bindings-and-isolated-frontend-test-harnesses.md): Add thin React bindings and isolated frontend test harnesses — **bridge source**
- [TASK-20](../../tasks/task-20%20-%20Enforce-scoped-file-network-and-browser-resource-authority.md): Enforce scoped file network and browser resource authority — **bridge source**
- [TASK-29](../../tasks/task-29%20-%20Prepare-and-qualify-0.3.0-release.md): Prepare and qualify 0.3.0 release

### 0.4.0

The bridge is consumed here (generated projects, packaged bundle) but should not change; a required change is a patch release of the bridge at its own version, and means an m-2 contract gap.

- [TASK-6](../../tasks/task-6%20-%20Implement-QGIS-Desktop-and-standalone-development-modes.md): Implement QGIS Desktop and standalone development modes
- [TASK-8](../../tasks/task-8%20-%20Build-a-validated-QGIS-installable-plugin-ZIP.md): Build a validated QGIS-installable plugin ZIP
- [TASK-16](../../tasks/task-16%20-%20Implement-non-mutating-check-and-QGIS-import-diagnostics.md): Implement non mutating check and QGIS import diagnostics
- [TASK-19](../../tasks/task-19%20-%20Scaffold-vanilla-and-React-web-projects-through-validated-questionnaires.md): Scaffold vanilla and React web projects through validated questionnaires
- [TASK-21](../../tasks/task-21%20-%20Implement-generation-safe-development-refresh-and-reconnection.md): Implement generation safe development refresh and reconnection
- [TASK-26](../../tasks/task-26%20-%20Implement-environment-aware-test-CLI-and-runtime-selection.md): Implement environment aware test CLI and runtime selection
- [TASK-30](../../tasks/task-30%20-%20Prepare-and-qualify-0.4.0-release.md): Prepare and qualify 0.4.0 release

### 0.5.0

- [TASK-9](../../tasks/task-9%20-%20Define-SDK-and-plugin-release-compatibility-gates.md): Define SDK and plugin release compatibility gates
- [TASK-22](../../tasks/task-22%20-%20Complete-and-qualify-the-local-GIS-reference-workflow.md): Complete and qualify the local GIS reference workflow
- [TASK-31](../../tasks/task-31%20-%20Prepare-and-qualify-0.5.0-release.md): Prepare and qualify 0.5.0 release

### 0.6.0

- [TASK-10](../../tasks/task-10%20-%20Prototype-an-optional-Rust-algorithm-backend-after-v1.md): Prototype an optional Rust algorithm backend after v1
- [TASK-32](../../tasks/task-32%20-%20Prepare-and-qualify-0.6.0-release-tentative-deferred-target.md): Prepare and qualify 0.6.0 release (tentative deferred target)
