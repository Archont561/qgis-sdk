---
id: decision-87
title: Render the web UI catalogue with Shopify Polaris web components
date: '2026-11-19'
status: accepted
---

## Context

`@archont561/qgis-sdk-ui` ships eleven Lit-based custom elements
(`<qgis-choice>`, `<qgis-layer-picker>`, `<qgis-run-button>`, …) that mirror
the Python `qgis_sdk.ui` catalogue. Each renders a native HTML control
(`<select>`, `<input>`, `<button>`) styled by the package's own stylesheet
from `--qgis-sdk-*` tokens. The elements work, but every control is
hand-built: the package owns the look, the accessibility, and the behaviour
of eleven controls, and a consumer who wants a different look restyles from
scratch.

Shopify Polaris ships a library of web components (`<s-button>`,
`<s-text-field>`, `<s-select>`, `<s-progress>`, …) that follow Shopify's
design system. They are maintained, accessible, and cover most of the
catalogue's needs. The user wants the web UI mode to render with Polaris
and is fine with the Shopify look.

Three constraints shape the integration:

1. **Polaris is CDN-only.** The web components ship as a single bundle
   (`https://cdn.shopify.com/shopifycloud/polaris-2.js`); there is no npm
   package for them. A QGIS web view reaches no remote origin (decision-43),
   so a plugin page cannot load the CDN script. The bundle must be vendored
   into the plugin's `web/` directory and bundled by Vite.
2. **Polaris expects App Bridge.** The docs load App Bridge alongside
   Polaris. App Bridge connects an app to Shopify admin; outside Shopify it
   is inert. The components render without it, but features that talk to the
   admin (toasts, modals) need the bridge. QGIS does not use those.
3. **The `<qgis-*>` API is public.** Existing pages use `<qgis-*>` elements
   with properties (`name`, `label`, `value`, `options`) and events
   (`qgis-change`, `qgis-result`). Replacing the elements with raw `<s-*>`
   components would break every consumer.

## Decision

Keep the `<qgis-*>` element API. Re-implement the rendering inside each
element with Polaris `<s-*>` components, behind a separate entry point
(`@archont561/qgis-sdk-ui/polaris`) so the default build is unchanged.

- Each element gains a Polaris-backed render path. When the Polaris
  elements are defined (the page loaded the vendored bundle), the element
  renders `<s-*>` components; otherwise it renders the native control it
  renders today. The properties, events, and store integration are
  identical in both paths.
- The mapping is one-to-one where Polaris has an equivalent
  (`<qgis-run-button>` → `<s-button>`, `<qgis-choice>` → `<s-select>`,
  `<qgis-job-progress>` → `<s-progress>`). Where Polaris has no equivalent
  (the QGIS-specific pickers), the element renders an `<s-select>` or
  `<s-text-field>` with the picker's options or value.
- The `polaris` entry point registers the Polaris-backed elements under
  the same tag names. A page imports either `define` (native) or `polaris`
  (Polaris), never both. The package documents the vendoring step: download
  `polaris-2.js`, place it in `web/`, load it before the elements.

## Consequences

- A plugin page gets the Shopify look by loading one vendored script and
  importing a different entry point. No page markup changes.
- The package carries two render paths per element. The native path stays
  the default and the tested path; the Polaris path is tested with stub
  `<s-*>` elements (the real bundle is CDN-only and cannot be fetched in
  CI).
- Polaris versioning is the consumer's: the vendored bundle's version is
  whatever the plugin ships. The package does not pin or update it.
- The QGIS palette theming (`applyHostTheme`, `--qgis-sdk-*` tokens) does
  not apply to Polaris components, which carry their own theme. A page that
  wants the QGIS palette uses the native entry point.
