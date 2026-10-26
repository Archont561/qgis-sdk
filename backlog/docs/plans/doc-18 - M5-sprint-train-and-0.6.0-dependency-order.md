---
id: doc-18
title: M5 sprint train and 0.6.0 dependency order
type: guide
created_date: '2026-10-26 09:20'
---
# M5 sprint train and 0.6.0 dependency order

**Status:** Planning. This document orders work the m-5 tasks already
declare; it adds no scope. Sprint membership lives here and in the milestone
body, not in task fields ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

**Baseline measured on 2026-10-26** at `56e074e` (after PR #90, the last
m-5 slice that landed): Python suite 1484 passed / 42 skipped,
`tests/scripts` 235 passed (`test_backlog.py` 15 after this plan). Bun and
coverage figures are re-measured at the start of sprint 1 and recorded here.

## 1. Where m-5 starts from

Released: Python `0.5.0` (`python-v0.5.0`, `386089b`), TypeScript `0.3.0`
(`ts-v0.3.0`). Already on `main` since, all documented in doc-12/doc-13's
0.6.0 notes: function-form `@job` (TASK-58, [decision-38](../../decisions/decision-38%20-%20Declare-jobs-as-plain-functions-with-the-JobContext-injected.md)), capability attributes
(TASK-59, [decision-39](../../decisions/decision-39%20-%20Expose-optional-services-as-capability-attributes-that-refuse-by-name.md)), the bridge root barrel and `QgisSdk`-prefixed generated
errors (TASK-61, [decision-40](../../decisions/decision-40%20-%20Make-the-root-entry-the-page-import-and-keep-generated-plugin-clients-import-free.md)), the release-owned scaffold pin (TASK-62, [decision-41](../../decisions/decision-41%20-%20Pin-the-scaffolded-page-to-the-released-bridge-and-switch-it-to-the-workspace-bridge-only-by-explicit-flag.md);
closure still to record).

What 0.5.0 did **not** do, because this milestone has to finish it:

| Gap | Why it matters in m-5 | Owner |
| --- | --- | --- |
| Algorithms are classes; `@job` and actions are functions | one authoring model, not two ([decision-42](../../decisions/decision-42%20-%20Declare-algorithms-as-plain-functions-on-providers-the-plugin-owns.md)) | **TASK-63** |
| The scaffold writes `webview.py`, `metadata.txt`, `classFactory` | the author's project must stay QGIS-free ([decision-43](../../decisions/decision-43%20-%20Generate-the-QGIS-host-artifacts-in-build-and-dev-instead-of-scaffolding-them.md)) | TASK-64, TASK-65 |
| The page builds its client from per-plugin generated validators | three statements, fully typed, `host` exposed ([decision-44](../../decisions/decision-44%20-%20Generate-a-typed-bridge-schema-module-and-build-the-client-from-it-at-runtime.md)) | TASK-66 |
| A native plugin has no way to put an action on a toolbar | `@toolbar`/`@menu`/`@shortcut` on `@action` ([decision-45](../../decisions/decision-45%20-%20Bind-actions-to-the-Desktop-with-stackable-toolbar-and-menu-decorators-and-plain-surface-classes.md)) | TASK-67 |

## 2. Dependency read of the m-5 tasks

| Task | Declared dependencies | State | Startable now |
| --- | --- | --- | --- |
| [TASK-63](../../tasks/task-63%20-%20Declare-algorithms-as-plain-functions-on-providers-the-plugin-owns.md) function algorithms | TASK-59 ✓ | To Do | **yes** |
| [TASK-66](../../tasks/task-66%20-%20Generate-the-typed-bridge-schema-module-and-add-QgisSdk.fromBridgeSchema.md) typed schema module + `fromBridgeSchema` | TASK-61 ✓ | To Do | **yes** (independent of 63) |
| [TASK-64](../../tasks/task-64%20-%20Generate-metadata.txt-classFactory-and-the-page-view-in-build-and-dev.md) generated host artifacts | TASK-63 | To Do | after 63 |
| [TASK-65](../../tasks/task-65%20-%20Scaffold-the-clean-project-and-migrate-the-reference-plugin.md) clean scaffold + reference migration | TASK-64 | To Do | after 64 |
| [TASK-67](../../tasks/task-67%20-%20Bind-actions-to-the-Desktop-with-toolbar-menu-shortcut-and-action-named-surfaces.md) desktop bindings + surfaces | TASK-64 | To Do | after 64 |
| [TASK-60](../../tasks/task-60%20-%20Prepare-and-qualify-0.6.0-release.md) 0.6.0 gate | TASK-31 ✓, 58 ✓, 59 ✓, 61 ✓, 62, 63–67 | To Do | release gate |

## 3. Sprint train

One pull request per sprint, because the session is bound to one branch;
commits inside keep the slices reviewable.

- **Sprint 1: TASK-63**, with the TASK-62 closure (Done, four ACs, "merged
  #90 → `56e074e`") as the first commit. `Provider(id, title)`,
  `@provider.algorithm(title=, group=)` on `def f(ctx: AlgorithmContext,
  layer: LayerInput, ...)`, `providers = [tools]` on the plugin class
  registered by the runtime, one `invoke(function, ctx, **inputs)`; the class
  form is removed and `qgis_sdk.reference` becomes `reference_provider`.
  Pure tests, the Processing registration under `QgisApplication`
  (`QGIS_SDK_REFERENCE=1`), doc-12's 0.6.0 note. The example's algorithms
  migrate here because the runtime refuses the class form afterwards.
- **Sprint 2: TASK-66.** `bridge generate` emits `web/src/bridge.schema.ts`
  (typed interfaces, `defineBridgeSchema`, `CONTRACT_FINGERPRINT`);
  `QgisSdk.fromBridgeSchema(schema, options?)` in the root with a method per
  action, a handle per stream, `host` typed from the package manifest with
  `host.granted`, `client`, `close()` and the default QWebChannel transport;
  per-plugin validators and `transport.ts` retire. Bridge 0.4.0 pending the
  gate; wire and `HOST_FINGERPRINT` unchanged and shown so. Can swap with
  sprint 1 if the Python slice stalls.
- **Sprint 3: TASK-64.** `[tool.qgis-sdk] plugin = "pkg.module:Class"`;
  `build` and `dev` render `metadata.txt`, bind `classFactory` through
  `qgis_sdk.adapters.desktop.host(spec)`, own the page view, and register
  the host operations named by `[tool.qgis-sdk.web] grants`; `dev` stages
  into `.qgis-sdk/dev/host/<plugin>/`; `check` gains META001/ENTRY002 and
  the unknown-grant finding. Opt-in `QGIS_SDK_BUILD_INSTALL=1` and
  `QGIS_SDK_DEVTOOLS=1` harnesses re-run.
- **Sprint 4: TASK-65.** The scaffold drops `webview.py`, `metadata.txt` and
  `classFactory`; the reference plugin in `examples/simple` migrates onto
  the generated artifacts and the schema module; doc-12/doc-13 and the
  guides describe the clean project; `QGIS_SDK_SCAFFOLD_DESKTOP=1`,
  `QGIS_SDK_SCAFFOLD_WEB=1` and `test-reference-example` pass.
- **Sprint 5: TASK-67.** `@toolbar`/`@menu`/`@shortcut` stacked on `@action`,
  `describe_bindings(cls)` outside `describe_plugin`, the trigger rules (no
  inputs → run; inputs → `NativeForms`; job → message bar; `dialog=`/`dock=`
  → a plain surface class with `build() -> QWidget`), icons through
  `qgis_sdk.resources`, `qgis-sdk new --ui native`; decision-12 promoted
  as narrowed. `QGIS_SDK_DESKTOP_ADAPTER=1` harness. **Separable:** if
  0.6.0 must ship earlier, this sprint moves to m-6 ahead of TASK-68.
- **Gate: TASK-60.** The 0.5.0 gate re-run over the new API ([doc-14](../guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)), the
  pair `python-v0.6.0` + `ts-v0.4.0` on one merge commit, only on an
  explicit "Release 0.6.0".

## 4. Hygiene done at sprint start

- Decisions 42–47 recorded on PR #91 before any code; decisions 7, 8, 9, 10,
  14, 23 promoted to `accepted` with dated reviews; 11, 12, 16 reviewed and
  left `proposed` with their promotion conditions named.
- m-6 re-pointed to the UI toolkit (0.7.0) and m-7 created for the deferred
  native-compute research (0.8.0; since re-pointed to agent access, the
  research is m-8 at 0.9.0); TASK-32 rewritten, TASK-71 created,
  TASK-10 moved ([m-6](../../milestones/m-6%20-%200.7.0-%E2%80%94-ui-toolkit-declaration-kinds%2C-native-surfa.md), [m-7](../../milestones/m-7%20-%200.8.0-%E2%80%94-agent-access-loopback-transport%2C-mcp-serve.md)).
- Pending: the TASK-62 closure (sprint 1, first commit).
