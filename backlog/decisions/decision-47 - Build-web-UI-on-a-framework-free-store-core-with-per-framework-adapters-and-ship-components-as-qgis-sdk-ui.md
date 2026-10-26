---
id: decision-47
title: Build web UI on a framework-free store core with per-framework adapters and ship components as qgis-sdk-ui
date: '2026-10-26'
status: accepted
---
## Context

decision-46 put the web half of the UI helpers inside `@archont561/qgis-sdk`:
headless `./react` bindings (point 3) and a `./ui` entry of themed controls
(point 4). Two follow-up questions changed the shape. First, whether
components - things that ship pixels, CSS and custom-element registration -
belong in a package whose job is transport and contract, which today has zero
runtime dependencies, one optional `react` peer and no side effects. Second,
the owner wants Vue and Svelte supported alongside React and vanilla web
components. A React-shaped `useOperation` cannot be ported three times without
behaviour drifting; what is affordable is one framework-free core and thin
adapters.

## Decision

1. **Headless core = stores, in the bridge root.** The behaviour behind the
   current `./react` hooks is reimplemented once as plain typed objects with
   the store contract - `getSnapshot()`, `subscribe(listener) → unsubscribe`,
   plus methods - and exported from the root of `@archont561/qgis-sdk`:
   `OperationStore<Op>` (`run`, `cancel`, state), `StreamStore<S>` (handle,
   last payload, `close`), `FormStore<Op>` (values, validity, `submit`),
   `HostQueryStore` (layers, CRS, fields; the grant-refusal state when
   `qgis.host.granted` lacks the operation). They are typed from the generated
   schema module of decision-44 and the host manifest, so the adapters inherit
   the type safety instead of restating it. The vanilla template consumes the
   stores directly. **No behaviour lives in an adapter**: anything that would
   need `if (framework === …)` goes into the core.
2. **One adapter per framework, each its own subpath and optional peer.**
   `./react` (`useSyncExternalStore`, `BridgeProvider` kept), `./vue`
   (composables returning `shallowRef`s, `provide`/`inject`, `onScopeDispose`),
   `./svelte` (the store contract *is* Svelte's store contract, so `$store`
   works unmodified; a runes wrapper for Svelte 5 idioms; `setContext`/
   `getContext`). Peers: `react >=18`, `vue >=3.4`, `svelte >=5`, all optional;
   each adapter is `external` in the build and about a hundred lines, mostly
   types. The public API of `./react` does not change; its internals move onto
   the stores.
3. **Components live in a new package, `@archont561/qgis-sdk-ui`.** Web
   components (`<qgis-declared-form>`, `<qgis-layer-picker>`, `<qgis-crs-picker>`,
   `<qgis-field-picker>`, `<qgis-job-progress>`, `<qgis-file-input>`) are the
   single implementation, built on the stores, Shadow-DOM scoped; framework
   wrappers are subpaths of the same package (`/react`, `/vue`, `/svelte`) that
   add typed props and events (`v-model`, `bind:value`, controlled props) over
   the elements and nothing else. The palette tokens (`--qgis-sdk-*` CSS
   variables seeded from the running QGIS palette by `host()`), the default
   CSS and the Storybook (`@storybook/web-components-vite`, mounted on
   `createBridgeHarness`) move here from decision-46 point 4 and 5. The package
   is a Bun workspace member at `packages/qgis-sdk-ui`, peer-depends on the
   bridge through a caret range, carries its own `ui` release scope
   (`ui-vX.Y.Z`, `release.py stamp --scope ui`), and is gated by the same
   release run as the bridge. An unscoped `qgis-sdk-ui` alias on npm follows
   the `qgis-sdk` alias pattern only if asked for.
4. **Tiered framework support, declared not implied.** *Tier 1* - vanilla and
   React: scaffold template, scaffold-web harness, docs page. *Tier 2* - Vue
   and Svelte: adapter and wrappers shipped, typed and tested in their own
   Vitest projects in the gate, a short wiring guide, no scaffold template. A
   framework is promoted to Tier 1 by one task that adds its template with
   exact pins (decision-18/41) and runs it through the harness; it is never
   promoted implicitly. The tiers are stated in doc-13 and in the package
   README.
5. **Testing.** The core is tested framework-free against `createBridgeHarness`;
   each adapter has one Vitest project (its own compiler); the web components
   and the wrappers are tested through portable stories, so the stories are the
   fixtures. Stories, Storybook configuration and framework wrappers' dev
   dependencies stay out of every published tarball.

## Consequences

- decision-46 is amended: point 3 becomes "store core in the root plus
  adapters"; point 4 and point 5 move to `@archont561/qgis-sdk-ui`. The
  bridge keeps zero runtime dependencies and no side effects; its release
  cadence stays tied to the contract.
- A third published artifact joins the pairing rule of decision-25: the UI
  package pins a bridge range, `verify-versions` checks that the range admits
  the workspace bridge, and the release gate states which bridge the UI ran
  against. Release tags: `python-v*`, `ts-v*`, `ui-v*`.
- Adding a framework later is one adapter plus, if wanted, one template - not
  a redesign. Dropping one is deleting a subpath in a minor.
- Costs accepted: two more Vitest projects in the gate, one more workspace
  member, one more README and alias decision, Vue and Svelte majors to track.
  Cost deferred: Vue and Svelte scaffold templates and their harness time.
- Deliberately not included: a general widget library, SSR, a Storybook per
  framework, framework-native reimplementations of the components.

## Amendment (2026-10-26, decision-55)

Component names mirror the native catalogue of decision-55: the web
component `qgis-declared-form` is `qgis-form`, and the set grows to the names
listed there (`DirectoryInput`, `Distance`, `Choice`, `LogView`,
`RunButton`). The store core, the adapters and the package split are
unchanged.
