---
id: decision-46
title: Ship UI helpers as declaration kinds, standard surfaces, headless web bindings and themed defaults
date: '2026-10-26 16:00'
status: accepted
---
## Context

After decisions 42-45 an author declares actions, algorithms, bindings and
surfaces in one file, and a page reaches them through `QgisSdk`. What the SDK
offers *inside* a surface or a page is thin. Natively, `qgis_sdk.ui` maps an
action's inputs to seven widget families (`text`, `integer`, `number`,
`boolean`, `layer`, `crs`, `metres`, plus `Literal` choices) and
`adapters/qgis/ui.py` renders them as one Qt dialog; everything else is
hand-written PyQt over `runtime.actions`. On the web side there are hooks
(`useOperation`, `useStream`, `BridgeProvider`) and the scripted harness, but
no component, no form renderer, no picker that knows about grants, no theme;
the React template is a bare `<button>`. decision-16's theme half
(`ctx.ui.theme`, tokens) has no consumer and is still proposed.

The temptation is a widget kit. The repository's rule is the opposite: one
declaration drives every host, the SDK refuses what it cannot represent, and
Qt and the browser each keep their own idioms. Helpers therefore have to
extend the *declaration vocabulary* and the *bridge-aware* pieces no UI
library can supply, and stop there.

## Decision

1. **More parameter kinds, each complete across hosts.** A kind is one marker
   in `qgis_sdk.models.parameters`, one widget family in `qgis_sdk.ui`, one
   Qt widget in the native form, one Processing parameter (decision-42) and
   one JSON-schema annotation the page can read. Added: `FileInput(filters=)`
   and `DirectoryInput()` (returning `FileRef`, decision-20, never a path),
   `FieldInput(of="<layer param>")` (an attribute field of a declared layer
   input), `Range(min, max)` on numbers, `Colour()`, and `Enum`/`Literal`
   choices for strings. A kind that cannot be rendered by every host is not
   added.
2. **Standard surfaces, named by actions.** Three surface classes ship in the
   runtime and are referenced the decision-45 way (`dialog=`/`dock=`):
   `DeclaredForm` (what `NativeForms` renders today, with `initial=` values and
   an `accept` hook), `JobProgressDock` (a job's stream as a progress panel
   with cancel), and `LogPanel`. `ctx.ui.form(action_id, initial=)` opens a
   declared form from inside a handler. `ctx.notifications` gains `warning`,
   `critical`, `success` and `with_action(label, action_id)`; it stays a
   service, not a widget. Map tools and custom widgets remain the documented
   escape hatch through `ctx.desktop`.
3. **Headless web bindings in `./react` and framework-free in the root.**
   `DeclaredForm` (renders an action's input schema and submits through
   `qgis`), `LayerPicker`/`CrsPicker`/`FieldPicker` (fed by `qgis.host`,
   disabled with a reason when the grant is absent), `JobProgress` (a stream
   handle to `{progress, state, cancel()}`), `FileRefInput` (a host picker
   handing back the `FileRef`). Each is a hook plus a render-prop component;
   the vanilla template gets the same logic as plain functions. No DOM
   styling is imposed by this tier.
4. **Themed defaults in `./ui`, seeded from QGIS.** A small set of form
   controls styled through CSS variables (`--qgis-sdk-accent`, spacing, font)
   that `host()` seeds from the running QGIS palette when the page opens, so
   a page looks native by default and overridable by design. This is
   decision-16's theme half, narrowed to palette tokens; rich declarative
   themes stay out.
5. **Storybook on the harness, inside the SDK only.** `packages/
   qgis-sdk-typescript` gains Storybook (`@storybook/react-vite`) whose
   stories mount each component in `BridgeProvider` over `createBridgeHarness`
   with scripted replies, faults and grants; the same stories are the Vitest
   fixtures through portable stories, and the static build is published with
   the docs site (TASK-43). Scaffolded plugins do not get Storybook; the
   in-QGIS offscreen Chromium harnesses remain the real-render evidence and
   no screenshot-diff service is added.

## Consequences

- Authors get, for free in both hosts: file and directory pickers that never
  expose paths, field pickers, ranges, colours, enums; a progress dock for
  jobs; a form that opens from a handler; notification levels. On the web:
  grant-aware pickers and a schema-driven form in three lines.
- The bridge contract does not change: new kinds are JSON-schema annotations
  the page may ignore, and the host surface is unchanged. New Processing
  parameter mappings are additive.
- `@archont561/qgis-sdk` grows two entries (`./react` additions, new `./ui`)
  and a `storybook` dev dependency set; its `files` whitelist keeps stories
  out of the published tarball.
- decision-16 is promoted once point 4 lands, by a status review naming the
  palette tokens as the agreed theme surface; decision-12 stays narrowed as
  decision-45 left it.
- Deliberately not included: a general widget library, Qt layout helpers,
  canvas tools as SDK objects, visual regression services.
- Scheduled as the 0.7.0 UI-toolkit release
  ([m-6](../milestones/m-6%20-%200.7.0-%E2%80%94-ui-toolkit-parameter-kinds%2C-curated-compon.md)):
  points 1–2 are [TASK-68](../tasks/task-68%20-%20Add-file-directory-field-range-colour-and-enum-parameter-kinds-the-catalogue-input-components-and-the-Form-helper.md),
  points 3 and 5 are [TASK-69](../tasks/task-69%20-%20Replace-the-react-internals-with-a-framework-free-store-core-and-add-vue-and-svelte-adapters.md),
  point 4 is [TASK-70](../tasks/task-70%20-%20Create-qgis-sdk-ui-web-components-on-the-store-core-React-Vue-and-Svelte-wrappers-palette-tokens-and-Storybook.md),
  and the gate is [TASK-32](../tasks/task-32%20-%20Prepare-and-qualify-0.7.0-release.md) together with the docs
  site ([TASK-43](../tasks/task-43%20-%20Publish-a-Starlight-documentation-site-from-the-backlog-guides.md)). Nothing here blocks 0.6.0.

## Amendment (2026-10-26): web half re-shaped by decision-47

[decision-47](../decisions/decision-47%20-%20Build-web-UI-on-a-framework-free-store-core-with-per-framework-adapters-and-ship-components-as-qgis-sdk-ui.md) changes points 3, 4 and 5 after two follow-up questions (should
components live in the bridge; how to support Vue and Svelte alongside React
and vanilla). Point 3 becomes a framework-free store core in the bridge root
with `./react`, `./vue` and `./svelte` adapters - the names listed above
survive as stores and as adapter bindings. Points 4 and 5 (themed `./ui`,
Storybook) move out of the bridge into `@archont561/qgis-sdk-ui`, where the
controls become web components with framework wrappers and the Storybook is
`@storybook/web-components-vite`. Points 1 and 2 (parameter kinds, native
surfaces) are untouched. Tasks: [TASK-68](../tasks/task-68%20-%20Add-file-directory-field-range-colour-and-enum-parameter-kinds-the-catalogue-input-components-and-the-Form-helper.md) (points 1–2), [TASK-69](../tasks/task-69%20-%20Replace-the-react-internals-with-a-framework-free-store-core-and-add-vue-and-svelte-adapters.md) (store
core and adapters), [TASK-70](../tasks/task-70%20-%20Create-qgis-sdk-ui-web-components-on-the-store-core-React-Vue-and-Svelte-wrappers-palette-tokens-and-Storybook.md) (`qgis-sdk-ui`), [TASK-72](../tasks/task-72%20-%20Promote-Vue-and-Svelte-to-Tier-1-with-scaffold-templates-and-harness-coverage.md) (Tier 1
promotion of Vue and Svelte, unscheduled).

## Amendment (2026-10-26, decision-55)

Point 1 (parameter kinds) stands and feeds `Form`, Processing, the wire and
the web. Point 2 is replaced: there are no "standard surfaces named by
actions"; `DeclaredForm` becomes the `Form` component placed in `build()`,
`JobProgressDock` becomes the `JobProgress` component (and a `Dock` an author
writes around it), `LogPanel` becomes `LogView`; `ctx.ui.form` becomes
`Form.for_action`. The notification levels stay. Point 3's components are
renamed to match (`Form`, `LayerPicker`, `CrsPicker`, `FieldPicker`,
`FileInput`, `JobProgress`); points 4 and 5 stand as absorbed by decision-47.
