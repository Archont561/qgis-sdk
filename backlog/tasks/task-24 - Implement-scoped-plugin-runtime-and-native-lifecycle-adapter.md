---
id: TASK-24
title: Implement scoped plugin runtime and native lifecycle adapter
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-21 21:56'
labels: []
milestone: m-1
dependencies:
  - TASK-2
  - TASK-11
  - TASK-23
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-12 -
    Use-one-context-injected-controller-per-UI-surface.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
  - doc-8
priority: medium
type: feature
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement scoped plugin runtime and native lifecycle adapter. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Construct plain author classes through explicit context/factories without constructor rewriting.
- [x] #2 Own/dispose actions, signals, dialogs/docks and work; repeated unload and partial startup failure are safe.
- [ ] #3 Provide focused pure lifecycle tests and real Desktop startup/unload evidence with no fake fallback.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Approved bounded slice: QGIS-free PluginRuntime with explicit context construction (default cls(context), optional instance factory), read-only bound action mapping, idempotent unload via the existing ResourceScope, and safe partial-startup cleanup. Add a delegating Desktop lifecycle adapter (classFactory/initGui/unload, lazy native boundary) and an opt-in headless QGIS lifecycle smoke. Pure tests own representative action/signal/dialog/work cleanups. Real Desktop startup/unload evidence remains open under TASK-33; do not claim AC3.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-17 session: user approved the bounded slice (pure runtime + Desktop adapter + action binding), construction seam cls(context) with explicit factory override, ResourceScope as sole ownership mechanism, and a PR that includes the reproduced TASK-2 post-merge closure. Environment is an unverified restore (nine RECORD mismatches); baseline 226 passed/1 skipped. No implementation claimed yet.

2026-10-17 bounded slice implemented (unverified restore environment; no dependency or lockfile changes):
- AC1: PluginRuntime validates declarations at construction, then constructs the plain class once via the default plugin_class(context) factory or an explicit instance_factory. It never inspects or rewrites the constructor; tests prove a constructor trap is bypassed and an undeclared class is never constructed. Declared actions bind to instance methods and expose a read-only ID mapping.
- AC2: unload closes the existing PluginContext.scope once and is safe to repeat, including from new, running and failed states. Partial startup failure releases already-registered action/signal/dialog-dock/work cleanups in reverse order, sets failed, and re-raises the author error with cleanup failures attached as __cause__. Unload cleanup failures still reach stopped, attempt all callbacks and raise ExceptionGroup. Pure tests include 16 runtime unit tests, three BDD scenarios, a Hypothesis repeated-unload property and five adapter tests.
- AC3 remains open: pure lifecycle tests are in place, but there is no real Desktop startup/unload evidence. The new headless harness runs the adapter inside a real QgsApplication with iface=None and no event loop; it is explicitly not a Desktop qualification. TASK-33 tracks the missing Desktop/Windows/macOS evidence.
Validation this session: root test 256 passed/2 opt-in smoke skipped; root coverage 231 passed/2 skipped, Python 100% (450 statements, runtime 88 and adapters/desktop 23 at 100%), bridge 90 passed at 100%; Ruff lint and scoped format, Biome, bridge typecheck, git diff --check, wheel/sdist build with Twine and bridge build pass. The opt-in headless lifecycle smoke passes against QGIS 4.2.3-Belém do Pará and Qt 6.11.2 (action ping=7, plugin started/unloaded, owned resources released, QGIS exited). Root build still fails at the known conda-forge repodata TLS handshake EOF. No merge yet.

2026-10-17 post-merge closeout: PR #13 merged into main as f9740a80ad0b0b2ba53b7ae19c21d12048b94198 (implementation 611e1ac020bfd21888aca967eb6f1f82e3e39179), merged by Archont561 with a merge commit. Post-merge main runs: CI 39052147058 succeeded (commit-message, lint, format, typecheck, skill tooling, Actions lint and coverage steps all passed) and publish sandbox 39052147023 succeeded. AC1 and AC2 are proven by the landed runtime/adapter modules and the tests included in this PR. AC3 stays open: there is still no real Desktop startup/unload evidence. The headless harness runs the adapter inside a real QgsApplication with iface=None, no display and no event loop, which is not a Desktop qualification; TASK-33 tracks that gap. The task therefore remains In Progress rather than Done. The local environment remains an unverified restore (nine dist-info/RECORD integrity mismatches), so this closure claims merged code and CI, not a verified environment. No dependency or lockfile changes.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC3 asks for real Desktop startup/unload evidence with no fake fallback. A display session is unreachable from here and ci.yml's `cross-platform (${ matrix.os })` job is dark until November, so AC3 stays open. The headless lifecycle smoke (QGIS_SDK_HEADLESS_LIFECYCLE=1, passed 2026-10-21) is recorded as headless evidence only and does not satisfy AC3.
---
<!-- COMMENTS:END -->
