---
id: doc-17
title: M4 sprint train and 0.5.0 dependency order
type: guide
created_date: '2026-10-25 17:45'
---
# M4 sprint train and 0.5.0 dependency order

**Status:** Planning plus the start of sprint 1. This document orders work the
m-4 tasks already declare; it adds no scope. Sprint membership lives here and
in the milestone body, not in task fields ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

**Baseline measured on 2026-10-25** at `d726861` (after `python-v0.4.0`):
Python suite 1369 passed / 38 skipped, coverage 96.19 %, `tests/scripts` 192
passed, Bun 197 passed (bridge 187 + alias 10). Every opt-in harness in
[doc-14](../guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)
passed one file per process for the 0.4.0 gate.

## 1. Where m-4 starts from

Released: Python `0.4.0` (`python-v0.4.0`, PR #76, closed by PR #77),
TypeScript `0.3.0` (`ts-v0.3.0`). The CLI is complete for the documented
workflow: `new`, `bridge generate`, `check`, `test`, `dev`, `build`. Inside
the one `qgis-sdk` wheel the runtime and the tools are already separate trees
with the layer test holding the boundary (TASK-56, decision-35 step 1).

What 0.4.0 did **not** do, because this milestone has to start from it:

| Gap | Why it matters in m-4 | Owner |
| --- | --- | --- |
| One wheel carries runtime and tools | a compatibility gate (TASK-9) cannot name a tested runtime range on a distribution that does not exist | **TASK-57** |
| No Windows evidence | the milestone's exit criterion is a Windows/Linux x86-64 matrix | TASK-22, TASK-33 (host blocker) |
| The bridge has never run inside a real `QWebEngineView` against a published `qgis-sdk` | the pair has to be qualified, not assumed | TASK-22 |
| `release.py` knows two scopes | a tools release without a runtime release is not expressible | TASK-57 (AC 2) |

## 2. Dependency read of the m-4 tasks

Read from the task files:

| Task | Declared dependencies | State | Startable now |
| --- | --- | --- | --- |
| [TASK-57](../../tasks/task-57%20-%20Cut-qgis-sdk-runtime-qgis-sdk-tools-and-the-qgis-sdk-meta-kit-as-three-distributions.md) three distributions | TASK-56 ✓, TASK-8 ✓, TASK-30 ✓ | Done (#78) | **yes** (decision-36 removed the freeze gate) |
| [TASK-22](../../tasks/task-22%20-%20Complete-and-qualify-the-local-GIS-reference-workflow.md) reference workflow | TASK-26 ✓ and the m-2/m-3 slices | Done (sprint 2) | Linux rows recorded; Windows rows blocked by host (TASK-33) |
| [TASK-9](../../tasks/task-9%20-%20Define-SDK-and-plugin-release-compatibility-gates.md) compatibility gates | TASK-8 ✓, TASK-22, TASK-23 | To Do | after 22; needs 57's ranges to say anything checkable |
| [TASK-31](../../tasks/task-31%20-%20Prepare-and-qualify-0.5.0-release.md) 0.5.0 gate | TASK-9, TASK-22, TASK-30 ✓ | To Do | release gate |

## 3. Sprint train

- **Sprint 1 (done 2026-10-25): TASK-57, one pull request (#78, merged as
  `60c1dc2`) in two commit series.** The two-PR plan collapsed into one branch because the
  session is bound to it; the commits keep the split reviewable. First the
  distributions: the tree moves to `packages/qgis-sdk-runtime`,
  `packages/qgis-sdk-tools` and the code-free kit in
  `packages/qgis-sdk-python`; `release.py stamp/verify-versions/build-python`
  treat the three manifests as one `python` scope at one version (kit pins
  `==X`, tools range `>=X,<X+0.1`, three wheels, three recipe outputs with
  exact subpackage pins); tests, scripts, CI, Pixi and coverage paths follow.
  Then the independent `runtime-v*`/`tools-v*` scopes with their own publish
  steps, the refusal of a tools release whose range excludes HEAD's runtime,
  the TestPyPI or `workflow_dispatch` rehearsal recorded in doc-14, the
  `qgis-sdk check` diagnostic for a pinned runtime or generated client
  outside the supported range, and the 0.5.0 migration note. The
  distributions come first because everything after them in this milestone
  talks about distributions by name. The prerelease tag `python-v0.5.0-rc.1`
  on the merge commit rehearsed the pipeline end to end (`release.yml` run
  40220722995: three wheels, three Conda outputs, every upload skipped;
  doc-14, "Split release pipeline rehearsal").
- **Sprint 2: TASK-22.** The reference workflow end to end over the CLI the
  milestone inherits, with the pure and native tests it declares, the web
  view through a real `QWebEngineView` against the published bridge, and the
  Linux evidence rows. Windows rows are recorded as blockers until a host
  exists (TASK-33). Landed as: the `qgis_sdk.exports` policy and
  `Layers.export_vector` (fake and native, one contract), the
  `reference/polygon-output` style, `examples/simple` (its own
  `LocalGisWorkflow` chain - the runtime stays free of workflow code - five
  actions, vanilla page, its own pure and `qgis` tests run by CI), the opt-in `tests/test_reference_example_native.py` that
  runs `new`/`check`/`bridge generate --check`/`test`/`build`/`dev` on the
  example and drives page and native dialog in one QGIS, and the evidence
  rows in doc-14 ("Reference plugin through the toolchain"). The bridge
  inside the real view is the published `@archont561/qgis-sdk` 0.3.0; no
  defect surfaced, so no bridge release.
- **Sprint 3: TASK-9.** The gates, written as checks: the explicit
  QGIS/Python/Qt/OS matrix, the tools-to-runtime range and the
  bridge-to-contract pair stated on the distributions TASK-57 created,
  `pixi lock --check` in the release path, and the metadata/build checks the
  release workflow already runs named as the gate.
- **Close: TASK-31.** Release gate only; the Python minor is the deliberate
  act (`--bump minor`), the bridge is published only if the matrix found a
  defect, and the stamp, tag and publication wait for explicit requests.

## 4. Hygiene done at sprint start

- [decision-36](../../decisions/decision-36%20-%20Cut-the-three-Python-distributions-before-the-contract-freeze.md)
  amends decision-35: the split no longer waits for the contract freeze; the
  freeze becomes the runtime's 1.0.
- TASK-57's description rewritten; AC 1, 2 and 4 checked on #78, AC 3 on
  the `python-v0.5.0-rc.1` rehearsal; closed Done.
- m-4's deliverables table lists the three Python distributions; doc-4's
  0.5.0 inventory points here.
- decision-15's presentation-state restore stays deferred without a task; it
  is not m-4 scope.
