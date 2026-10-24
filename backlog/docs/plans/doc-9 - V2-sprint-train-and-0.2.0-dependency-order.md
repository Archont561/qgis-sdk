---
id: doc-9
title: V2 sprint train and 0.2.0 dependency order
type: guide
created_date: '2026-10-24 14:14'
---
# V2 sprint train and 0.2.0 dependency order

**Status:** Planning only. This document changes no task status, claims no
implementation, and adds no scope. It orders work that the tasks already
declare, and records which task should start milestone m-1.

**Baseline measured on 2026-10-24** at `1d956a8` (after the `v0.1.1` release):
`pixi run -e bun bun run test` → 408 passed, 6 skipped (the skips are the
opt-in native smoke suites). No test, coverage or CI result beyond that was
re-measured for this document.

## 1. Where v2 starts from

v1 is out: `v0.1.0` (2026-10-24T13:35Z) and `v0.1.1`
(2026-10-24T14:02Z, PRs #43 and #44) are published, and the release gate
[TASK-27](../../tasks/task-27%20-%20Prepare-and-qualify-0.1.0-release.md) is
closed. Milestone m-1 is the next milestone and reads 2/8 done
([TASK-1](../../tasks/task-1%20-%20Scaffold-a-QGIS-plugin-project-from-the-CLI.md),
[TASK-24](../../tasks/task-24%20-%20Implement-scoped-plugin-runtime-and-native-lifecycle-adapter.md)).

What the package actually contains today, because the sprint plan has to start
from this and not from the architecture it intends to become:

| Area | Present in `packages/qgis-sdk/src/qgis_sdk` | Missing for 0.2.0 |
| --- | --- | --- |
| `declarations.py` | Decorators, annotation walker, generated description | Actions/forms rendering (TASK-3) |
| `core/` | `PluginRuntime`, `ResourceScope`, `StepScheduler`/`Job`/`Handoff`, four contexts | Job submission API and typed result handles (TASK-15) |
| `services/contracts.py` | Five Protocols only: `Notifications`, `Cancellation`, `Progress`, `ViewControl`, `DesktopAccess` | Layers, project, settings, styles, networking (TASK-25, TASK-5) |
| `adapters/` | `desktop` lifecycle, `webengine`, `pydantic` contract validation | PyQGIS-backed services (TASK-25) |
| `scaffold/` | Project generation CLI | Packaging and dev loop (m-3) |

There is no Processing module and no HTTP client yet, so TASK-14 and TASK-5 are
greenfield work rather than extensions.

The TypeScript side is not part of this train. 0.2.0 publishes no bridge version
at all: no m-1 task changes `packages/qgis-sdk-bridge`, so it stays at 0.1.1 and
nothing is consumed from npm. The release still checks the shared
plugin-description contract version, and the typed surface is m-2's work. See the
"Bridge track" section of
[m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md).

## 2. Dependency read of the remaining 0.2.0 tasks

Every row is read from the task files, not inferred:

| Task | Declared dependencies | State | Startable now |
| --- | --- | --- | --- |
| [TASK-25](../../tasks/task-25%20-%20Implement-curated-native-services-and-packaged-style-support.md) curated native services and packaged QML | TASK-24 ✓ | To Do | **yes** |
| [TASK-14](../../tasks/task-14%20-%20Implement-class-based-Processing-algorithms-and-safe-outputs.md) classified Processing algorithms, safe outputs | TASK-24 ✓, TASK-25 | To Do | no — blocked by TASK-25 |
| [TASK-3](../../tasks/task-3%20-%20Render-schema-driven-native-UI-and-dispatch-Python-handlers.md) schema-driven native UI and handler dispatch | TASK-24 ✓, TASK-25 | To Do | no — blocked by TASK-25 |
| [TASK-15](../../tasks/task-15%20-%20Implement-scoped-local-jobs-and-typed-result-handles.md) scoped local jobs and typed handles | TASK-13 ✓, TASK-24 ✓ | To Do | yes |
| [TASK-5](../../tasks/task-5%20-%20Add-a-QGIS-aware-HTTP-client-and-typed-GIS-service-layer.md) QGIS-aware HTTP client and typed GIS services | TASK-13 ✓, TASK-24 ✓ | To Do | yes |
| [TASK-28](../../tasks/task-28%20-%20Prepare-and-qualify-0.2.0-release.md) 0.2.0 release gate | TASK-1 ✓, TASK-3, TASK-5, TASK-14, TASK-15, TASK-24 ✓, TASK-25, TASK-27 ✓ | To Do | no — release gate |

The graph therefore has exactly one gateway: **TASK-25 unblocks TASK-14 and
TASK-3**, and those two are the largest remaining features. The critical path is
`TASK-25 → (TASK-14, TASK-3) → TASK-28`. TASK-5 and TASK-15 are unblocked but
unblock nothing, which makes them parallel candidates rather than the start.

## 3. Sprint 1 — start with TASK-25

**Sprint 1 goal:** land the curated native service contracts and their PyQGIS
adapter, so that TASK-14 and TASK-3 can be opened against contracts that exist
instead of inventing them mid-feature.

Why TASK-25 and not another unblocked task:

- It is the only task on the critical path that can start now. Starting TASK-15
  or TASK-5 first delays the milestone by one full increment, because both only
  feed TASK-28.
- Contract-first avoids rework: TASK-14 needs layer/output ownership and
  project addition after success, and TASK-3 needs the same layer and
  notification capabilities for its actions. Those semantics are decided once,
  in TASK-25, or twice under two features.
- Its styling half is directly required by the accepted reference workflow
  ([decision-19](../../decisions/decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md)),
  and later by TASK-22. It is cheaper to qualify packaged QML now than after
  Processing outputs exist.
- Evidence is obtainable locally: QGIS `4.2.3` and `pyqt6-webengine` are pinned
  in `pixi.toml`'s `qgis` feature, and the existing opt-in harnesses
  (`packages/qgis-sdk/scripts/*.py`) already drive real QGIS headless.

**Parallel track (best effort, not part of sprint 1's exit criteria):**
TASK-15 builds directly on the landed `StepScheduler`, so it is the cheapest
second stream; TASK-5 is the alternative when the service contracts are in
review. Take one, not both, and never at the cost of the TASK-25 landing.

**Explicitly out of sprint 1:** TASK-14 and TASK-3 (they consume TASK-25's
contracts), and TASK-28.

### Suggested slices inside TASK-25

These five slices are now tracked on the board as sub-tasks of TASK-25
(`TASK-25.1`–`TASK-25.5`), because the parent's three criteria span contracts, a
native adapter, settings, styling and qualification — more than one change set can
prove. Their dependency shape: `25.1` first, `25.2` and `25.3` in parallel on it,
`25.4` on `25.2`, and `25.5` on `25.2`+`25.3`+`25.4`.

Each slice should be independently reviewable and should keep the suite green:

1. **Contracts and fakes.** Add only the layer, project, settings and style
   capabilities the reference workflow needs, as Protocols in
   `qgis_sdk.services` with in-memory fakes for tests. No PyQGIS mirror
   ([decision-6](../../decisions/decision-6%20-%20Separate-models-services-core-and-runtime-adapters.md));
   extend `tests/test_pure_imports.py` so the boundary keeps being enforced.
2. **Native layer and project adapter.** PyQGIS-backed implementations with
   explicit lifetime, selection, output-ownership and scoped-resource
   semantics, plus fake/native parity tests.
3. **Settings and notifications.** Scoped settings access and the notification
   capability behind the existing `Notifications` Protocol.
4. **Packaged QML.** Apply a reviewed style resource to a compatible output
   through the layer service, validate layer/field/geometry compatibility, and
   do not touch the global stylesheet
   ([decision-16](../../decisions/decision-16%20-%20Separate-reusable-layer-styles-from-UI-themes.md)).
5. **Evidence and records.** An opt-in harness proving output ownership and
   selection against real QGIS `4.2.3`, plus the TASK-25 notes recording what
   the headless host can and cannot prove.

### Sprint 1 is done when

- TASK-25's three acceptance criteria are checked with recorded evidence, not
  with intent.
- `pixi run -e bun bun run test` and `pixi run -e bun bun run coverage` pass,
  with the touched modules at the repository's 100% convention and the Codecov
  90% gate intact.
- `pixi run lint-python`, `pixi run format-python-check` and the TypeScript checks
  are clean, and `git diff --check` is empty.
- TASK-14 and TASK-3 are unblocked on the board: no dependency on TASK-25
  remains, and the contracts they need are importable and documented.

## 3a. Sprint 1 outcome (2026-10-24)

TASK-25 and all five slices are `Done`. Evidence:
[doc-11](doc-11%20-%20TASK-25-native-services-qualification-evidence.md).

| Slice | Result |
| --- | --- |
| TASK-25.1 | Layers/Project/Settings/Styles contracts + in-memory fakes, `qgis_sdk.testing` |
| TASK-25.2 | `NativeLayers`/`NativeProject` on PyQGIS, post-close refusal as contract |
| TASK-25.3 | `NativeSettings` (prefixed `QgsSettings`), `NativeNotifications` (unwidened Protocol) |
| TASK-25.4 | reviewed packaged QML catalog, shared compatibility rule, theme proven unchanged |
| TASK-25.5 | headless qualification on QGIS 4.2.3, six explicit non-claims |

Both of sprint 1's exit conditions are met: TASK-25's criteria are checked with
recorded evidence, and **TASK-14 and TASK-3 are unblocked** — their TASK-25
dependency is the only one that was missing.

What sprint 1 did **not** change: TASK-5 and TASK-15 are still open and still feed
only the release gate, and TASK-33's AC #1/#2 (Windows, Desktop GUI) remain the
only display-dependent blockers.

## 4. Sprint 2 and sprint 3 sketch

- **Sprint 2 — TASK-14 + TASK-3.** Both consume the TASK-25 contracts. TASK-14
  owns non-destructive output semantics, projected-CRS/units validation and
  project addition only after success; TASK-3 owns rendering declared actions
  and forms and dispatching validated values. Landing them together keeps the
  one shared contract set coherent.
- **Sprint 3 — TASK-5 and TASK-15 remainder, then TASK-28.** Close the
  networking and job streams, then run the release gate. TASK-28 is a gate, not
  permission: it needs verified outcomes plus explicit publishing approval and
  must not claim checks that did not run.

## 5. Verification commands

```sh
# first run in a fresh checkout only
pixi run -e bun bun install --frozen-lockfile

pixi run -e bun bun run test           # local suite, no coverage gate
pixi run -e bun bun run coverage       # separate Python/TypeScript 90% checks
pixi run lint-python
pixi run format-python-check
pixi run -e bun typecheck

# opt-in real-QGIS harnesses, e.g.
pixi run -e default python packages/qgis-sdk/scripts/desktop_lifecycle_smoke.py
```

The harnesses stay opt-in through their `QGIS_SDK_*` environment flags; the
QGIS-free tests for them live in `packages/qgis-sdk/tests/scripts/`.

## 6. Risks and blockers

- **Headless sandbox.** The Linux host has no display server, and
  `QT_QPA_PLATFORM=offscreen` renders no widgets, canvas, 3D or in-Desktop
  WebEngine view. Sprint 1 may claim service, ownership and style-application
  behaviour; it may not claim GUI rendering, Windows or macOS qualification.
  Those stay with TASK-33 (AC #1 and AC #2 open).
- **Release authority.** TASK-28 requires explicit publishing approval. An epic
  or sprint closing is not a release decision, and experimental 0.x breaking
  changes still need a documented minor release (doc-4).
- **Environment.** The `conda-forge` repodata TLS failure that blocked the
  Conda package build is environmental, not a code signal; record it rather
  than retrying differently. The Pixi restore in this workspace has been
  reported as unverified in earlier sessions, so qualify toolchain claims.
- **CI availability.** GitHub Actions is usable again as of 2026-10-24 (PR #38),
  so a merge should check the real runs rather than the outage protocol in
  [doc-8](doc-8%20-%20GitHub-Actions-outage-window-and-the-no-CI-evidence-protocol.md).
- **Scope discipline.** TASK-25 is a curated slice, not a service manager for
  all of PyQGIS; every added capability has to be used by a real workflow.

## 7. References

- [TASK-38](../../tasks/task-38%20-%20Epic-v2-0.2.0-native-runtime-and-Processing-algorithms.md) — the epic this plan serves.
- [m-1](../../milestones/m-1%20-%200.2.0-%E2%80%94-native-runtime-and-processing-algorithms.md) — 0.2.0 milestone.
- [doc-4](doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md) — version policy and task inventory.
- [doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md) — the vocabulary, predicate and slicing rules this plan follows.
- [decision-6](../../decisions/decision-6%20-%20Separate-models-services-core-and-runtime-adapters.md), [decision-16](../../decisions/decision-16%20-%20Separate-reusable-layer-styles-from-UI-themes.md), [decision-19](../../decisions/decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md).

## 3b. TASK-14 outcome (2026-10-24)

TASK-14 is `Done`: one decorated plain class per algorithm, `describe_algorithm`
without construction, a fresh instance and `AlgorithmContext` per invocation, and
an `Algorithms` service whose native backend writes a new output, refuses a
geographic or non-metre working CRS, cleans up on failure and hands nothing to the
project before success. Evidence is in the task notes (pure `497`, native `553`,
`tests/services` `100`, coverage `100%`), not in a separate document, because the
claims are the tests themselves.

decision-11 stays `proposed`: class-per-algorithm and fresh-per-invocation are
implemented, but provider/catalog registration, `QgsProcessingAlgorithm`/
`createInstance`, mid-flight cancellation and thread-affinity proofs are not.

m-1 is now 9/14. Remaining: TASK-3, TASK-5, TASK-15, and TASK-28 as the gate.

Follow-on: **TASK-39** (provider registration) was opened and completed the same
day, after TASK-14 made algorithms inspectable. A `Provider` now registers
algorithms that appear in the QGIS Processing toolbox and run through
`processing.run`, which is the registration object decision-11 described as
illustrative. TASK-39 joined m-1 (it *is* the "Processing algorithms" half of
that milestone's title), so the milestone is now fifteen tasks and stands at
10/15; the remaining four are TASK-3, TASK-5, TASK-15 and the TASK-28 gate.
