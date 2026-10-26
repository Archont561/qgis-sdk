---
id: doc-19
title: M6 sprint train and 0.7.0 dependency order
type: guide
created_date: '2026-10-26 09:20'
---
# M6 sprint train and 0.7.0 dependency order

**Status:** Planning; nothing starts before the TASK-60 gate closes 0.6.0.
This document orders work the m-6 tasks already declare; it adds no scope.
Sprint membership lives here and in the milestone body, not in task fields
([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

**Baseline:** measured at the start of sprint 1, on the commit that
`python-v0.6.0` and `ts-v0.4.0` were tagged on; recorded here then.

## 1. Where m-6 starts from

Expected from m-5: one authoring model (functions on providers, `@job`,
`@action` with stacked bindings), a clean scaffold whose host artifacts are
generated, a page that is typed from `bridge.schema.ts` and reaches curated
services through `qgis.host` under pyproject grants. What is still thin, and
what this milestone adds ([decision-46](../../decisions/decision-46%20-%20Ship-UI-helpers-as-declaration-kinds-standard-surfaces-headless-web-bindings-and-themed-defaults.md), [decision-47](../../decisions/decision-47%20-%20Build-web-UI-on-a-framework-free-store-core-with-per-framework-adapters-and-ship-components-as-qgis-sdk-ui.md)):

| Gap | Owner |
| --- | --- |
| Seven widget families, no file/directory/field/range/colour/enum kinds; `NativeForms` is the only native UI the SDK offers; `ctx.notifications.info` only | **TASK-68** |
| No way to wire a widget signal or a stream to a surface method without raw Qt bookkeeping; no containers, feedback or buttons; no fake rendering of surfaces; no `Custom` escape hatch (decision-55) | **TASK-96** |
| `./react` hooks are React-shaped; no Vue or Svelte path; the vanilla template re-implements the hooks' logic by hand | **TASK-69** |
| No components, no theme tokens, no Storybook; the page looks like a browser inside QGIS | **TASK-70** |
| No docs site; guides live in the backlog; the Storybook build has nowhere to publish | **TASK-43** |
| `pandas`-class imports are refused by `build` with no honest external path and no pure-Python vendoring (decision-50) | **TASK-77** |
| The QGIS Python console reaches a plugin only through `qgis.utils.plugins[name].runtime` and the vendored import path; no curated session (decision-48) | **TASK-73** |

## 2. Dependency read of the m-6 tasks

| Task | Declared dependencies | Language | Startable |
| --- | --- | --- | --- |
| [TASK-69](../../tasks/task-69%20-%20Replace-the-react-internals-with-a-framework-free-store-core-and-add-vue-and-svelte-adapters.md) store core + `./vue` + `./svelte` | TASK-66 | TypeScript | at milestone start |
| [TASK-68](../../tasks/task-68%20-%20Add-file-directory-field-range-colour-and-enum-parameter-kinds-the-catalogue-input-components-and-the-Form-helper.md) kinds + input components + `Form` | TASK-67, TASK-63 | Python | at milestone start |
| [TASK-96](../../tasks/task-96%20-%20Add-surface-wiring-and-the-rest-of-the-native-catalogue-on-subscribe-ui-loading-behaviour-mixins-containers-feedback-Custom-and-the-fake-rendering.md) wiring + mixins + containers + feedback + `Custom` | TASK-67, TASK-68 | Python | after 68 |
| [TASK-73](../../tasks/task-73%20-%20Add-qgis_sdk.console-ConsoleSession-over-the-curated-services-PluginHandle-and-PluginRuntime.algorithms.md) `qgis_sdk.console` | TASK-63, TASK-64 | Python | at milestone start |
| [TASK-77](../../tasks/task-77%20-%20Declare-externals-with-a-startup-probe-vendor-pure-Python-packages-in-build-and-bucket-imports-in-check.md) externals probe + pure-Python vendoring | TASK-64 | Python | at milestone start |
| [TASK-70](../../tasks/task-70%20-%20Create-qgis-sdk-ui-web-components-on-the-store-core-React-Vue-and-Svelte-wrappers-palette-tokens-and-Storybook.md) `qgis-sdk-ui` + `ui` release scope | TASK-69, TASK-64 | TypeScript + `release.py` | after 69 |
| [TASK-43](../../tasks/task-43%20-%20Publish-a-Starlight-documentation-site-from-the-backlog-guides.md) docs site | — | Astro Starlight | any time; placed last so it publishes the Storybook build |
| [TASK-32](../../tasks/task-32%20-%20Prepare-and-qualify-0.7.0-release.md) 0.7.0 gate | TASK-60, 68, 96, 69, 70, 73, 77, 43 | — | release gate |
| [TASK-72](../../tasks/task-72%20-%20Promote-Vue-and-Svelte-to-Tier-1-with-scaffold-templates-and-harness-coverage.md) Vue/Svelte Tier 1 | TASK-69, TASK-70 | — | **unscheduled**, no milestone |

## 3. Sprint train

- **Sprint 1: TASK-69.** `OperationStore`, `StreamStore`, `FormStore`,
  `HostQueryStore` in the bridge root, typed from the generated schema and
  the host manifest; `./react` re-based on them with its exports unchanged
  (`react.test.ts` must pass as is); `./vue` and `./svelte` as optional
  peers and separate build entries, each with its own Vitest project; one
  behaviour suite run against the core and through each adapter; the Tier 1
  / Tier 2 table in doc-13 and the README. Bridge-only; no Python change.
- **Sprint 2: TASK-68.** The six kinds end to end (marker, widget family,
  catalogue input, Processing parameter, JSON-schema annotation; the
  describer refuses a kind missing any of the four); the eleven input
  components wrapping QGIS widgets, model-valued, stream-refreshed, with
  fake renderings; `Form.for_action`/`from_schema`/`fields`; `NativeForms`
  removed with the migration in doc-12's 0.7.0 note; notification levels
  and `with_action`; the example builds its buffer dialog from `Form`. **TASK-73** rides in the same pull request as a
  second commit series: `qgis_sdk.console.connect()`, `ConsoleSession`,
  `PluginHandle`, `DesktopLifecycleAdapter.console()`,
  `PluginRuntime.algorithms`, the dev recipe and the doc-12 console section.
  **TASK-77** is a third series in the same pull request or its own small
  one: externals as tables with the startup probe in the generated
  `classFactory`, `metadata.txt` rendering, `vendor = [...]` with DEP003/
  DEP004, import buckets in `check`. Python-only; swaps with sprint 1 freely.
- **Sprint 3: TASK-96.** `@on`/`@subscribe`/`ctx.on`, `on_accept`/`on_close`,
  `ui=` loading, `RunsJobs`/`SubscribesStreams`/`AcceptCancel`, the
  containers, feedback and button components, `Custom`, the QWidget-class
  surface form, `ui_snapshot` under the fake, echo flag, UI002/UI004; the
  example's results panel becomes a `Dock` built from the catalogue.
- **Sprint 4: TASK-70.** `packages/qgis-sdk-ui` as a workspace member: the
  web components named as the native catalogue on the stores, `/react`, `/vue`, `/svelte` wrappers,
  `--qgis-sdk-*` tokens seeded by `host()`, Storybook on
  `createBridgeHarness` with portable stories as fixtures, the `ui` scope in
  `release.py` (`stamp`, `verify-versions` peer-range check, `plan`),
  `files` whitelist, README per decision-29; the Tier 1 templates opt in
  through one import; decision-16 promoted. The webengine palette test
  needs a QGIS host (Linux CI has one).
- **Sprint 5: TASK-43.** The Starlight site from the backlog guides with
  the Storybook static build mounted under it, deployed by a `docs.yml`
  workflow to GitHub Pages; the root README gains the docs badge and link
  and loses nothing else (decision-29).
- **Gate: TASK-32.** Three artifacts in one run: `python-v0.7.0`, the next
  `ts-v*` minor and `ui-v0.1.0` on one merge commit, fingerprints shown
  unchanged, both npm packages recorded as run against the 0.7.0 runtime.
  Only on an explicit "Release 0.7.0".

## 4. Hygiene to do at sprint start

- Re-measure the baseline and fill in section 0 of this document.
- If sprint 5 of [m-5](../../milestones/m-5%20-%200.6.0-%E2%80%94-API-ergonomics-function-jobs-and-capability-attributes.md) (TASK-67) slid here, it runs before TASK-68 and the
  m-6 body's sprint train is amended, not this document's history.
- Confirm the bridge version the UI package will peer-range on (0.4.0 or
  later) once `ts-v0.4.0` exists; the task AC already refuses a range that
  excludes the workspace bridge.
