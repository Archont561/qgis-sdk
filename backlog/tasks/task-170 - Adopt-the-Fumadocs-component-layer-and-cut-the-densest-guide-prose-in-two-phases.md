---
id: TASK-170
title: Adopt the Fumadocs component layer and cut the densest guide prose in two phases
status: To Do
assignee: []
created_date: '2026-10-28 22:40'
labels: []
dependencies: []
references:
  - apps/docs/scripts/generate.ts
  - apps/docs/scripts/lib/guides.ts
  - apps/docs/scripts/postbuild.ts
  - apps/docs/app/[...slug]/page.tsx
  - apps/docs/content/docs
  - apps/docs/guides
  - api/python.json
priority: medium
type: docs
ordinal: 170000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The site already runs on Fumadocs (fumadocs-ui 16.18.4, fumadocs-core, fumadocs-mdx 15.5.3, Next 16.4.5, React 19.3.1, static export under basePath /qgis-sdk), and it uses almost none of it: measured on cbdc41d, the corpus has zero Steps, zero Tabs, zero Files, zero TypeTable, zero Accordion, zero Callout and zero ::: asides across 108 pages - only Card/Cards on the landing and roadmap. Prose carries what components should: 101,539 words of non-code prose across 108 pages, average 941 a page, with four generated pages holding roughly a fifth of it (desktop-bindings 3,989, host-namespaces 3,008, scoped-jobs 2,887, desktop-host 2,604). Two probes on 2026-10-28 established the three constraints this task exists to satisfy: a component in a .mdx page fails the build unless it is registered (Expected component Steps to be defined), JSX in a .md page is silently dropped while the build stays green - the failure mode that would let a component rollout ship rendering nothing - and 97 of the 108 pages are generated from three .md guide sources that are also read on GitHub, so JSX cannot simply be authored into them. Scope is the component layer and the six pages that carry the most prose; type tables come from the committed inventory rather than AutoTypeTable, and no CSS pipeline change is included.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One component registry in apps/docs (lib/mdx.tsx) supplies Callout, Card/Cards, Steps, Tabs/Tab, Files/Folder/File, TypeTable, Accordion/Accordions, Banner, InlineTOC and ImageZoom to both app/[...slug]/page.tsx and app/page.tsx, so a page needs no import of its own; a test asserts the registry is the only components map either route passes.
- [ ] #2 The generator emits .mdx for every guide-derived page (apps/docs/content/docs/{python,typescript,contributing}), the .md export URLs stay byte-identical because postbuild writes them independently, and the docs suite plus next build pass with no page renamed.
- [ ] #3 A generated-page component gate fails the build when a page whose source carries a component directive renders without that component's markup; the gate is proven against a deliberately unregistered component and against JSX placed in a .md page, so the silent-drop failure mode cannot ship.
- [ ] #4 Guide sources stay readable on GitHub: components are introduced through a documented, plain-text directive layer expanded by the generator (remark plugin or directive blocks), and a test asserts no JSX tag appears in apps/docs/guides/*.md.
- [ ] #5 Five guide-derived pages carry components instead of paragraphs - python/scoped-jobs (question headings as Accordions), typescript/host-namespaces (one service per Tab), python/desktop-bindings-and-native-surfaces (catalogue as TypeTable, tree as Files), python/project-scaffold (Files) and python/desktop-host-host-and-the-project-manifest (Steps or Files, whichever the section is) - with no page's link count falling and no heading anchor lost.
- [ ] #6 The two hand-written guides (guides/test-a-plugin, guides/web-plugin) use Steps, and start/installation.mdx uses Tabs for the pip, pixi and from-source paths, each tab carrying a copyable command and its working directory.
- [ ] #7 TypeTable content is generated from api/python.json (name, shape, tier, the guide section that explains it) rather than typed by hand or produced through fumadocs-typescript, and the docs suite fails when a stable name in the inventory has no row.
- [ ] #8 Prose is reduced by at least 25 percent on the five AC 5 pages and start/installation, measured by a scripted word count with fenced code and tables excluded; the numbers are recorded in this task against the cbdc41d baseline in the description, and /reference/api-index (table density, not prose) is explicitly out of scope for the target.
- [ ] #9 Nothing is lost in the swap: internal link count does not fall (check-links was 11,128 on cbdc41d), the docs boundary suite still passes, every removed paragraph is accounted for as either moved to a reference page or proven redundant in the implementation notes, and the accessibility qualifications in TASK-138 AC 2 hold (text alternatives, keyboard access, contrast, responsive).
- [ ] #10 The decision is recorded: this task supersedes TASK-138 AC 2, 3, 4, 7, 8, 10 and 11 and adds them as dependencies of that record, while TASK-138 keeps AC 1, 5, 6, 9 and 12 for the components it owns; TASK-130, TASK-132, TASK-135 and TASK-136 keep their own scopes and are neither duplicated nor pre-empted.
- [ ] #11 The rejected paths are stated in the implementation notes with the reason, so they are not re-proposed: no UnoCSS or PostCSS swap (zero text reduction, re-implements fumadocs' own Tailwind v4 theme layer), no AutoTypeTable (fumadocs-typescript needs built .d.ts and plain next build in apps/docs does not build packages first), no graph view (no such export in fumadocs-ui 16.18.4), no landing or robots/sitemap rebuild (both already ship and are green).
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Four phases in this order; each ends green before the next starts.

**P0 - foundation, no content edits.** Build the registry (AC 1), switch generated pages to .mdx (AC 2), and land the gate first (AC 3), because a component rollout without it is unfalsifiable. Add the directive layer (AC 4) in the same phase: the guide sources are read on GitHub and are the canonical explanation (decision-29), so components are expanded by the generator, not authored inline.

**P1 - the pages that hold the words.** Convert the six targets (AC 5, AC 6), in this order: desktop-bindings (largest), host-namespaces, scoped-jobs, project-scaffold, desktop-host, then the three hand-written pages. Each page is one commit with its before/after count, so a reviewer can reject one page without losing the rest.

**P2 - type tables from the inventory.** Render api/python.json into TypeTable blocks (AC 7), reusing the module note map the API index already needs, so a stable name cannot lose its row.

**P3 - accounting and records.** The 25 percent gate with its measuring script (AC 8), the loss audit against the 11,128-link baseline (AC 9), and the board records that keep this from being rediscovered: supersession of the TASK-138 criteria and the rejected paths (AC 10, AC 11).

Ordering rationale: AC 3 before AC 5 because the silent-drop probe showed a green build with no component rendered; AC 4 before AC 5 because retrofitting directives onto converted pages would repeat the work; AC 7 after AC 5 because the TypeTable rows only make sense once each page's sections have their final shape.
<!-- SECTION:PLAN:END -->
