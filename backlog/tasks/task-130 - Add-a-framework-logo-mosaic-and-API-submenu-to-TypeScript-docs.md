---
id: TASK-130
title: Add a framework logo mosaic and API submenu to TypeScript docs
status: To Do
assignee: []
created_date: '2026-10-28 16:07'
labels: []
dependencies: []
references:
  - apps/docs/astro.config.ts
  - apps/docs/guides/doc-13 - qgis-sdk-TypeScript-package-guide.md
  - apps/docs/scripts/generate.ts
  - >-
    backlog/tasks/task-72 -
    Promote-Vue-and-Svelte-to-Tier-1-with-scaffold-templates-and-harness-coverage.md
priority: medium
type: enhancement
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner wants a TypeScript documentation submenu showing supported frameworks as a mosaic of logos; selecting a framework should open that framework’s QGIS SDK API documentation. Add a Frameworks entry beneath TypeScript SDK leading to a visual, accessible landing page. The existing SDK ships React, Vue and Svelte adapters and a framework-free TypeScript store core: link to the relevant SDK API, not the frameworks’ external documentation. Preserve the documented distinction between adapter support and scaffold/qualification tiers; verify status against the implementation rather than implying all have equivalent support. Existing framework guide pages already exist at /typescript/react-bindings/, /typescript/vue-bindings/ and /typescript/svelte-bindings/, and the vanilla core is /typescript/stores-the-framework-free-core/. The reference guide pages are generated from apps/docs/guides/doc-13 and the generator clears its output directories, so place or generate the new page through a durable source, not a hand-edited generated page. No release milestone is assigned.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 TypeScript SDK navigation includes a discoverable Frameworks submenu entry leading to a responsive, visually coherent mosaic of recognizable React, Vue and Svelte logos with visible labels. Include a clearly labeled framework-free or Vanilla TypeScript route to the existing core documentation; do not present it as a framework or claim unsupported integrations.
- [ ] #2 Each framework card links directly to the matching QGIS SDK framework-specific API or bindings documentation, including correct import entry points and usage examples; enrich the existing reference source if a destination lacks the needed API information. Link the framework-free option to its core API. Clearly distinguish SDK bridge adapters from optional UI component wrappers and current support tiers.
- [ ] #3 Cards are real accessible links usable by mouse, touch and keyboard, with descriptive names, visible focus, appropriate image alternatives, sufficient contrast and responsive layout in supported light/dark themes; logos use attributable, appropriately licensed assets stored locally, and functionality does not depend on third-party runtime requests.
- [ ] #4 Preserve existing TypeScript guide URLs, migration and historical redirects, edit links and searchability. Avoid duplicate sidebar entries and generated-file overwrites; ensure all destinations and assets honor the /qgis-sdk/ GitHub Pages base and trailing-slash conventions.
- [ ] #5 Add automated coverage for navigation, framework-to-destination mappings, supported labels and local assets, including a representative responsive/keyboard accessibility check where the test harness permits; run docs tests, production docs build and internal-link checks with no broken links.
<!-- AC:END -->
