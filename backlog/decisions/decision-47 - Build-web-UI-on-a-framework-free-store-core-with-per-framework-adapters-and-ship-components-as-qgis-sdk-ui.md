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

## Amendment (2026-10-26, implementation choices for `qgis-sdk-ui`)

1. **Lit, in light DOM.** The components are authored with Lit (`lit` is
   the package's only runtime dependency, caret-pinned, an *evolving*
   detail under decision-56: consumers see custom elements, not Lit),
   written in the `static properties` form so plain TypeScript and bunup
   compile them like the bridge. `createRenderRoot()` returns the element:
   **no Shadow DOM**. The page is the plugin's own, so encapsulation buys
   little, while light DOM gives ordinary labels, focus order, form
   participation and consumer CSS. `<slot>` is therefore unavailable; the
   catalogue is leaf components, and `Form`/`Panel` compose by properties.
   One `StoreController` (a ReactiveController over the store contract)
   joins the decision-47 stores to Lit's update cycle; components hold no
   bridge logic. React wrapper through `@lit/react`; Vue and Svelte
   wrappers are typed thin shims (props, events, the `isCustomElement`
   note); no generated-wrapper toolchain. Stencil is declined: its value is
   compiler-generated wrappers and types, its price a second build system
   in a workspace with a settled one.
2. **UnoCSS as the authoring tool, compiled CSS as the product.** Templates
   use UnoCSS utilities from `preset-mini` with the `qs-` prefix and
   `preflights: false`; the package build runs UnoCSS over its own sources
   and ships `dist/style.css`, which a consumer imports with no UnoCSS of
   their own. The theme maps colours, spacing and type to `var(--qgis-sdk-*)`,
   so the palette `host()` seeds at page open still switches at runtime.
   No inline `style=`. Semantic hooks are `data-part="label|control|error"`
   for consumer overrides and `data-qgis-sdk="<name>"` as the stable id
   (the web twin of `objectName`, decision-51). An optional
   `@archont561/qgis-sdk-ui/uno` preset exports the theme and shortcuts for
   pages that use UnoCSS; the scaffold offers the Vite plugin as a question
   defaulting to off. Storybook keeps the `web-components-vite` builder
   with the UnoCSS plugin in its own config only.
3. **Consequence.** A component is a widget for pages the plugin owns, not
   a drop-in for arbitrary hosts; doc-13 says so. TASK-70 gains ACs for the
   no-UnoCSS consumer path, the prefix collision test, the CSS size budget
   and light-DOM accessibility.

## Status review (2026-10-27, TASK-110): the `ui` train publishes, stays `accepted`

Point 3's package reaches npm the way the bridge does. `release.yml` gains
a `ui` job gated on the classify flag: it builds the bridge and the
components, refuses a tarball holding anything but `dist`, `package.json`,
`README.md` and `LICENSE`, installs the scoped package and its alias from
the tarballs next to the bridge built in the same run, checks the alias
mirrors the exports and `@import`s the stylesheets, and publishes both
under trusted publishing (an `-rc.N` tag dry-runs under `next`). The
unscoped alias `qgis-sdk-ui` (`packages/qgis-sdk-ui-alias`) takes the
shape of decision-33's `qgis-sdk` alias - one re-export line per entry,
one `@import` per stylesheet, an exact pin, Bun tests that hold it to the
scoped package file for file - because the owner provisioned both names on
npm. `stamp --scope ui` moves the package, the alias and its pin, and
`UI_NPM_VERSION` in `scaffold/web.py`; `verify-versions --scope ui` names
whichever lags. The `ui` train still never rides an alignment release.
