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

`qgis-sdk` and `@archont561/qgis-sdk` **version independently** ([decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)). Each package derives its own version from the conventional commits that touch it, starting from its own last release tag; `python-v*` stamps `pyproject.toml` and `recipe.yaml`, `ts-v*` stamps the bridge `package.json`, and `v*` is a deliberate alignment release that stamps all three. What holds a pair together is the plugin-description **contract version** (`PLUGIN_DESCRIPTION_SCHEMA_VERSION`), declared once per language and checked by `release.py verify-versions` on every release; wire protocol versions stay independent of package versions. Within a milestone, feature and fix work bumps only the patch; the minor advances on a breaking change or when a milestone closes by an explicit `--bump minor`/`--version-override`, **per package**. Existing unreleased 0.1.0 metadata is not proof of a published usable release. The 0.7.0 reservation (re-pointed from 0.6.0 on 2026-10-25, when the API-ergonomics changes took that number) is tentative deferred research and requires renewed approval, not a Rust-shipping commitment.

## Milestones and release tasks

| Milestone | Python version (`qgis-sdk`) | Python deliverable | Bridge version (`@archont561/qgis-sdk`) | Bridge deliverable | Release gate |
| --- | --- | --- | --- | --- | --- |
| 0.1.0 [m-0](../../milestones/m-0%20-%200.1.0-%E2%80%94-architecture-and-qualification-spikes.md) | 0.1.0 → 0.1.1, published | Contracts, declarations, scheduler spikes | 0.1.0 → 0.1.1, published | Wire primitives: description parsing, safe integers, error hierarchy | [TASK-27](../../tasks/task-27%20-%20Prepare-and-qualify-0.1.0-release.md) |
| 0.2.0 [m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md) | **0.2.0** | Native runtime, Processing algorithms, UI dispatch | **stays at 0.1.1 — not released** | No source change; no npm version consumed | [TASK-28](../../tasks/task-28%20-%20Prepare-and-qualify-0.2.0-release.md) |
| 0.3.0 [m-2](../../milestones/m-2%20-%200.3.0-%E2%80%94-typed-bridge-runtime-web-ui-networking-and-local-jobs.md) | **0.3.0** | Transport host side, per-view authority, generated fixtures, HTTP client, local jobs (carried over from 0.2.0) | **0.2.0** | Transport contract, generated clients, React helpers, resource authority | [TASK-29](../../tasks/task-29%20-%20Prepare-and-qualify-0.3.0-release.md) |
| 0.4.0 [m-3](../../milestones/m-3%20-%200.4.0-%E2%80%94-developer-workflow-and-plugin-packaging.md) | **0.4.0** | Scaffolds, check/test/dev/build, ZIP packaging | **unchanged (0.3.0, the rename release of 2026-10-24)** | New consumers (generated projects), not new surface | [TASK-30](../../tasks/task-30%20-%20Prepare-and-qualify-0.4.0-release.md) |
| 0.5.0 [m-4](../../milestones/m-4%20-%200.5.0-%E2%80%94-qualified-experimental-reference-release.md) | **0.5.0**, published 2026-10-25 (`python-v0.5.0`: kit, runtime and tools) | Three distributions, qualified reference workflow, support matrix and compatibility gates | **unchanged (0.3.0): no defect found** | Qualified as a pair through a real WebEngine view against 0.5.0 | [TASK-31](../../tasks/task-31%20-%20Prepare-and-qualify-0.5.0-release.md) |
| 0.6.0 [m-5](../../milestones/m-5%20-%200.6.0-%E2%80%94-API-ergonomics-function-jobs-and-capability-attributes.md) | **0.6.0**, planned (runtime, tools and kit together) | Function-form `@job` (decision-38) and capability attributes replacing `require_<name>()` (decision-39) - both already on `main`, documented in doc-12's 0.6.0 migration notes; the generated contract error becomes `QgisSdkContractError` (decision-40) | **0.4.0**: root entry re-exports `./bridge`, idle error mirrors and `isPlainRecord` leave the root, `./host` exports `QgisSdkHostContractError` (decision-40, [TASK-61](../../tasks/task-61%20-%20Make-the-bridge-root-entry-the-page-import-and-prefix-the-generated-contract-errors.md)); wire unchanged | Paired: `ts-v0.4.0` stamped and tagged by the same gate as `python-v0.6.0` | [TASK-60](../../tasks/task-60%20-%20Prepare-and-qualify-0.6.0-release.md) |
| 0.7.0 [m-6](../../milestones/m-6%20-%200.7.0-%E2%80%94-deferred-native-compute-feasibility-%28tenta.md) | tentative | Deferred research only | no release | None planned; nothing published unless revived | [TASK-32](../../tasks/task-32%20-%20Prepare-and-qualify-0.7.0-release-tentative-deferred-target.md) |

## Bridge across milestones

The two artifacts are published independently, so each milestone's **Bridge track** opens with a table of concrete changes and the bridge version each one produces, then explains the ones it declined to make. There are three states:

- **Released with its own version** — 0.3.0 ([m-2](../../milestones/m-2%20-%200.3.0-%E2%80%94-typed-bridge-runtime-web-ui-networking-and-local-jobs.md)) is the only milestone that changes bridge source, and it releases the bridge at **0.2.0** (a minor set explicitly at the close) while Python ships 0.3.0. The numbers differ because the histories differ, which is the point of [decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md).
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
- [TASK-33](../../tasks/task-33%20-%20Qualify-Windows-macOS-and-Desktop-QGIS-targets.md): Qualify Windows, macOS and Desktop QGIS targets
- [TASK-34](../../tasks/task-34%20-%20Optimize-CI-cost-and-latency.md): Optimize CI cost and latency
- [TASK-37](../../tasks/task-37%20-%20Add-milestone-triggered-autorelease-and-CI-optimizations-from-playtest-patterns.md): Add milestone triggered autorelease and CI optimizations from playtest patterns

### 0.2.0

No task in this milestone changes `packages/qgis-sdk-typescript`, so the 0.2.0 release publishes only the Python package and the bridge stays at 0.1.1 (see [m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md)).

Re-scoped on 2026-10-24: TASK-5 and TASK-15 moved to 0.3.0, because they block nothing here, sit outside the milestone's name, and were both still waiting on decisions that are only `proposed` (decision-4, decision-13). TASK-3 is the last open feature.

- [TASK-1](../../tasks/task-1%20-%20Scaffold-a-QGIS-plugin-project-from-the-CLI.md): Scaffold a QGIS plugin project from the CLI
- [TASK-3](../../tasks/task-3%20-%20Render-schema-driven-native-UI-and-dispatch-Python-handlers.md): Render schema-driven native UI and dispatch Python handlers
- [TASK-14](../../tasks/task-14%20-%20Implement-class-based-Processing-algorithms-and-safe-outputs.md): Implement class based Processing algorithms and safe outputs
- [TASK-24](../../tasks/task-24%20-%20Implement-scoped-plugin-runtime-and-native-lifecycle-adapter.md): Implement scoped plugin runtime and native lifecycle adapter
- [TASK-25](../../tasks/task-25%20-%20Implement-curated-native-services-and-packaged-style-support.md): Implement curated native services and packaged style support
- [TASK-28](../../tasks/task-28%20-%20Prepare-and-qualify-0.2.0-release.md): Prepare and qualify 0.2.0 release
- [TASK-39](../../tasks/task-39%20-%20Register-provider-algorithms-in-the-QGIS-Processing-toolbox.md): Register provider algorithms in the QGIS Processing toolbox
- [TASK-38](../../tasks/task-38%20-%20Epic-v2-0.2.0-native-runtime-and-Processing-algorithms.md): Epic for this milestone. A tracking container only, with no scope of its own; the sprint order it encodes is in [doc-9](doc-9%20-%20V2-sprint-train-and-0.2.0-dependency-order.md).

### 0.3.0

The only milestone that changes bridge source, and the only one that releases the bridge on its own version (0.2.0). The remaining tasks are the Python-side contract and fixture work they depend on.

- [TASK-4](../../tasks/task-4%20-%20Add-the-versioned-WebEngine-bridge-contract.md): Add the versioned WebEngine bridge contract — **bridge source**
- [TASK-5](../../tasks/task-5%20-%20Add-a-QGIS-aware-HTTP-client-and-typed-GIS-service-layer.md): Add a QGIS-aware HTTP client and typed GIS-service layer — moved from 0.2.0
- [TASK-7](../../tasks/task-7%20-%20Add-layered-pytest-support-and-BDD-fixtures.md): Add layered pytest support and BDD fixtures
- [TASK-15](../../tasks/task-15%20-%20Implement-scoped-local-jobs-and-typed-result-handles.md): Implement scoped local jobs and typed result handles — moved from 0.2.0
- [TASK-17](../../tasks/task-17%20-%20Generate-checked-in-TypeScript-contracts-clients-and-validators.md): Generate checked in TypeScript contracts clients and validators — **bridge source**
- [TASK-18](../../tasks/task-18%20-%20Add-thin-React-bindings-and-isolated-frontend-test-harnesses.md): Add thin React bindings and isolated frontend test harnesses — **bridge source**
- [TASK-20](../../tasks/task-20%20-%20Enforce-scoped-file-network-and-browser-resource-authority.md): Enforce scoped file network and browser resource authority — **bridge source**
- [TASK-29](../../tasks/task-29%20-%20Prepare-and-qualify-0.3.0-release.md): Prepare and qualify 0.3.0 release
- [TASK-40](../../tasks/task-40%20-%20Refuse-a-malformed-paging-cursor-instead-of-restarting-the-first-page.md): Refuse a malformed paging cursor instead of restarting the first page — from the 2026-10-24 host-surface audit
- [TASK-41](../../tasks/task-41%20-%20Make-register_host_operations-atomic-and-reject-unknown-only-ids.md): Make register_host_operations atomic and reject unknown only ids — from the 2026-10-24 host-surface audit
- [TASK-42](../../tasks/task-42%20-%20Refuse-generated-type-names-that-collide-with-the-emitters-own-identifiers.md): Refuse generated type names that collide with the emitter's own identifiers — from the 2026-10-24 host-surface audit
- [TASK-44](../../tasks/task-44%20-%20Make-a-re-entrant-jobs.tick-a-no-op-instead-of-failing-the-running-job.md): Make a re-entrant jobs.tick() a no-op instead of failing the running job — from the 2026-10-25 scoped-jobs audit
- [TASK-45](../../tasks/task-45%20-%20Add-the-scoped-jobs-Gherkin-feature-and-parametrise-the-declaration-refusals.md): Add the scoped-jobs Gherkin feature and parametrise the declaration refusals — from the 2026-10-25 scoped-jobs audit
- [TASK-46](../../tasks/task-46%20-%20Make-handle.result-raise-the-jobs-own-failure-like-get-does.md): Make handle.result raise the job's own failure like get() does — from the 2026-10-25 scoped-jobs audit
- [TASK-47](../../tasks/task-47%20-%20Release-explicit-owner-subscription-hooks-when-a-job-finishes.md): Release explicit-owner subscription hooks when a job finishes — from the 2026-10-25 scoped-jobs audit
- [TASK-48](../../tasks/task-48%20-%20Give-derived-JobService-instances-a-complete-constructor.md): Give derived JobService instances a complete constructor — from the 2026-10-25 scoped-jobs audit
- [TASK-49](../../tasks/task-49%20-%20Share-one-declaration-describer-and-a-Description-protocol-across-plugin-algorithm-and-job.md): Share one declaration-describer and a Description protocol across plugin, algorithm and job — from the 2026-10-25 duplication scan

### 0.4.0

The bridge is consumed here (generated projects, packaged bundle) but should not change; a required change is a patch release of the bridge at its own version, and means an m-2 contract gap.

- [TASK-6](../../tasks/task-6%20-%20Implement-QGIS-Desktop-and-standalone-development-modes.md): Implement QGIS Desktop and standalone development modes
- [TASK-8](../../tasks/task-8%20-%20Build-a-validated-QGIS-installable-plugin-ZIP.md): Build a validated QGIS-installable plugin ZIP
- [TASK-16](../../tasks/task-16%20-%20Implement-non-mutating-check-and-QGIS-import-diagnostics.md): Implement non mutating check and QGIS import diagnostics
- [TASK-19](../../tasks/task-19%20-%20Scaffold-vanilla-and-React-web-projects-through-validated-questionnaires.md): Scaffold vanilla and React web projects through validated questionnaires
- [TASK-21](../../tasks/task-21%20-%20Implement-generation-safe-development-refresh-and-reconnection.md): Implement generation safe development refresh and reconnection
- [TASK-26](../../tasks/task-26%20-%20Implement-environment-aware-test-CLI-and-runtime-selection.md): Implement environment aware test CLI and runtime selection
- [TASK-30](../../tasks/task-30%20-%20Prepare-and-qualify-0.4.0-release.md): Prepare and qualify 0.4.0 release
- [TASK-35](../../tasks/task-35%20-%20Add-autorelease-and-release-workflows-driven-by-a-pinned-qgis-sdk-release-package.md): Add autorelease and release workflows driven by a pinned qgis-sdk-release package
- [TASK-36](../../tasks/task-36%20-%20Extract-qgis-sdk-release-into-a-standalone-checksum-pinned-repository.md): Extract qgis-sdk-release into a standalone checksum pinned repository
- [TASK-50](../../tasks/task-50%20-%20Rename-the-scaffold-CLI-command-to-new.md): Rename the scaffold CLI command to new — `scaffold` stays a hidden, deprecated alias for one minor
- [TASK-51](../../tasks/task-51%20-%20Derive-declaration-ids-and-titles-from-names-by-default.md): Derive declaration ids and titles from names by default — deterministic, explicit values win (decision-30)
- [TASK-52](../../tasks/task-52%20-%20Bind-PluginContext-as-the-ctx-class-attribute-instead-of-a-constructor-argument.md): Bind PluginContext as the ctx class attribute instead of a constructor argument (decision-31)
- [TASK-53](../../tasks/task-53%20-%20Offer-the-curated-services-on-PluginContext-and-build-the-web-view-surface-from-it.md): Offer the curated services on PluginContext and build the web-view surface from it (decision-32)
- [TASK-54](../../tasks/task-54%20-%20Rename-the-npm-package-to-archont561-qgis-sdk-and-suffix-the-package-directories.md): Rename the npm package to @archont561/qgis-sdk and suffix the package directories (decision-33)
- [TASK-55](../../tasks/task-55%20-%20Publish-qgis-sdk-as-an-unscoped-npm-alias-of-archont561-qgis-sdk.md): Publish qgis-sdk as an unscoped npm alias of @archont561/qgis-sdk (decision-33)
- [TASK-56](../../tasks/task-56%20-%20Split-the-SDK-tree-into-qgis_sdk-runtime-and-qgis_sdk_tools-inside-one-wheel.md): Split the SDK tree into qgis_sdk (runtime) and qgis_sdk_tools inside one wheel (decision-35, step 1)

### 0.5.0

- [TASK-9](../../tasks/task-9%20-%20Define-SDK-and-plugin-release-compatibility-gates.md): Define SDK and plugin release compatibility gates
- [TASK-22](../../tasks/task-22%20-%20Complete-and-qualify-the-local-GIS-reference-workflow.md): Complete and qualify the local GIS reference workflow
- [TASK-31](../../tasks/task-31%20-%20Prepare-and-qualify-0.5.0-release.md): Prepare and qualify 0.5.0 release
- [TASK-57](../../tasks/task-57%20-%20Cut-qgis-sdk-runtime-qgis-sdk-tools-and-the-qgis-sdk-meta-kit-as-three-distributions.md): Cut qgis-sdk-runtime, qgis-sdk-tools and the qgis-sdk meta kit as three distributions (decision-35 step 2, un-gated by decision-36; ordered in [doc-17](doc-17%20-%20M4-sprint-train-and-0.5.0-dependency-order.md))

### 0.6.0

Re-pointed on 2026-10-25: the two breaking API changes that followed 0.5.0 take the next minor; the deferred native-compute research moves to 0.7.0.

- [TASK-58](../../tasks/task-58%20-%20Redesign-job-as-a-plain-function-with-the-JobContext-injected.md): Redesign @job as a plain function with the JobContext injected (decision-38; landed on PR #86)
- [TASK-59](../../tasks/task-59%20-%20Expose-optional-context-services-as-capability-attributes-that-refuse-by-name.md): Expose optional context services as capability attributes that refuse by name (decision-39; landed on PR #87)
- [TASK-61](../../tasks/task-61%20-%20Make-the-bridge-root-entry-the-page-import-and-prefix-the-generated-contract-errors.md): Make the bridge root entry the page import and prefix the generated contract errors (decision-40; bridge 0.4.0 joins the pair)
- [TASK-60](../../tasks/task-60%20-%20Prepare-and-qualify-0.6.0-release.md): Prepare and qualify 0.6.0 release (Python 0.6.0 + bridge 0.4.0)

### 0.7.0

- [TASK-10](../../tasks/task-10%20-%20Prototype-an-optional-Rust-algorithm-backend-after-v1.md): Prototype an optional Rust algorithm backend after v1
- [TASK-32](../../tasks/task-32%20-%20Prepare-and-qualify-0.7.0-release-tentative-deferred-target.md): Prepare and qualify 0.7.0 release (tentative deferred target)
