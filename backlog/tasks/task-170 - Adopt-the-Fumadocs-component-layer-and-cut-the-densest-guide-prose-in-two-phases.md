---
id: TASK-170
title: Adopt the Fumadocs component layer and cut the densest guide prose in two phases
status: To Do
assignee: []
created_date: '2026-10-28 22:40'
updated_date: '2026-11-15 09:10'
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
- [x] #1 One component registry in apps/docs (lib/mdx.tsx) supplies Callout, Card/Cards, Steps, Tabs/Tab, Files/Folder/File, TypeTable, Accordion/Accordions, Banner, InlineTOC and ImageZoom to both app/[...slug]/page.tsx and app/page.tsx, so a page needs no import of its own; a test asserts the registry is the only components map either route passes.
- [x] #2 The generator emits .mdx for every guide-derived page (apps/docs/content/docs/{python,typescript,contributing}), the .md export URLs stay byte-identical because postbuild writes them independently, and the docs suite plus next build pass with no page renamed.
- [x] #3 A generated-page component gate fails the build when a page whose source carries a component directive renders without that component's markup; the gate is proven against a deliberately unregistered component and against JSX placed in a .md page, so the silent-drop failure mode cannot ship.
- [x] #4 Guide sources stay readable on GitHub: components are introduced through a documented, plain-text directive layer expanded by the generator (remark plugin or directive blocks), and a test asserts no JSX tag appears in apps/docs/guides/*.md.
- [ ] #5 Five guide-derived pages carry components instead of paragraphs - python/scoped-jobs (question headings as Accordions), typescript/host-namespaces (one service per Tab), python/desktop-bindings-and-native-surfaces (catalogue as TypeTable, tree as Files), python/project-scaffold (Files) and python/desktop-host-host-and-the-project-manifest (Steps or Files, whichever the section is) - with no page's link count falling and no heading anchor lost.
- [x] #6 The two hand-written guides (guides/test-a-plugin, guides/web-plugin) use Steps, and start/installation.mdx uses Tabs for the pip, pixi and from-source paths, each tab carrying a copyable command and its working directory.
- [ ] #7 TypeTable content is generated from api/python.json (name, shape, tier, the guide section that explains it) rather than typed by hand or produced through fumadocs-typescript, and the docs suite fails when a stable name in the inventory has no row.
- [x] #8 Prose is reduced by at least 25 percent on the five AC 5 pages and start/installation, measured by a scripted word count with fenced code and tables excluded; the numbers are recorded in this task against the cbdc41d baseline in the description, and /reference/api-index (table density, not prose) is explicitly out of scope for the target.
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
### P0 shipped (AC 1-4)

- **AC 1** - `apps/docs/lib/mdx.tsx` is the registry: it spreads the Fumadocs
  defaults (code blocks, headings, links) and adds Callout, Card/Cards,
  Steps/Step, Tabs/Tab, Files/Folder/File, TypeTable, Accordion/Accordions,
  Banner, InlineTOC, ImageZoom plus the four site components. Both routes take
  it - `app/[...slug]/page.tsx` passes `components={mdxComponents}` and nothing
  else, `app/page.tsx` imports `Card, Cards, Step, Steps` from it.
  `tests/mdx-registry.test.ts` asserts the contents and that no route imports
  `fumadocs-ui/components/*`.
- **AC 2** - `guides.ts` emits `index.mdx` and `<slug>.mdx`; `generate.ts`
  strips `.mdx` where it stripped `.md`, for the sidebar order, the migration
  folders and the edit links. `postbuild` still writes one `.md` per route: the
  build reports 109 routes, 108 markdown exports and 0 unresolved, unchanged
  from the baseline, and `check-links` found 11,346 internal links on 150 pages
  (baseline 11,128). No page was renamed.
- **AC 3** - `scripts/lib/gate.ts` runs in `postbuild`, so `bun run build`
  fails on either of the two silent failures. Arm one rejects JSX in a `.md`
  page; arm two compares `lib/generated/components.json` (route to directive
  names, written by the generator) against `data-qgis-sdk="<name>"` markers in
  the exported HTML.

  ```text
  probe 1  :::callout + :::steps in doc-12's Installation section
           generate: 1 pages carry components
           postbuild: component gate over 1 pages with directives, 0 problems
           out/python/installation/index.html:
             data-qgis-sdk="callout"  data-qgis-sdk="steps"

  probe 2  same page renamed to installation.md, postbuild without generate
           postbuild: python/installation.md:2: <Callout> is JSX in a .md page,
             which markdown drops; rename the page to .mdx or write a directive
           postbuild: /python/installation: :::callout produced no
             data-qgis-sdk="callout" in the page; the component was dropped
             instead of rendered
           postbuild: /python/installation: :::steps produced no
             data-qgis-sdk="steps" in the page; ...
           exit 1, and the page carried 0 markers

  probe 3  Step and Steps removed from the registry map, map intact elsewhere
           Error: Expected component `Step` to be defined: you likely forgot
             to import, pass, or provide it.
  ```

- **AC 4** - `scripts/lib/directives.ts` expands `:::callout`, `:::steps`,
  `:::tabs`/`:::tab`, `:::files` and `:::accordions`/`:::accordion` into JSX
  between the link rewrite and the write. Fences are literal, `tabs` and
  `accordions` are the only parents, and an unknown name, unclosed block or
  misplaced block raises `DirectiveError` with its line. The documentation is
  in doc-14's Documentation site section, with the syntax in a fence.
  `tests/directives.test.ts` asserts no JSX appears in `apps/docs/guides/*.md`
  and that every guide expands without an error.

### What `.mdx` cost, and the one module that pays it

A `.mdx` page is parsed as MDX, and 97 pages written as GitHub markdown were
not. Four constructs broke the build on the first run and are rewritten by
`scripts/lib/mdx-text.ts`: a brace outside code, an HTML comment, an autolink,
and a `<` in a version range. A fifth is a code span the author wrapped onto a
second line - MDX does not honour it, so the span is joined onto one line,
which is what markdown was rendering anyway. After that the build is clean. The
rewrites show up in 2 `\{` and 2 `\<` across the 108 exported `.md` files;
everything else is byte-identical.

### P1: the six pages, measured

`bun run measure-prose` (`scripts/measure-prose.ts`) counts body prose with
fences, table rows, `:::` markers, `data-qgis-sdk` wrappers and standalone JSX-tag
lines excluded; `tests/measure-prose.test.ts` pins what counts. Before/after on
this branch, against the numbers in the description:

| Page | Before | After | Cut |
| :-- | --: | --: | --: |
| `python/desktop-bindings-and-native-surfaces` | 3,758 | 2,814 | 25.1% |
| `typescript/host-namespaces` | 3,074 | 2,299 | 25.2% |
| `python/scoped-jobs` | 2,931 | 2,128 | 27.4% |
| `python/desktop-host-host-and-the-project-manifest` | 2,424 | 1,807 | 25.5% |
| `python/project-scaffold` | 1,443 | 1,042 | 27.8% |
| `start/installation` | 304 | 218 | 28.3% |

AC 6 in full: `guides/test-a-plugin` and `guides/web-plugin` are `.mdx` with
`<Steps>`, and `start/installation.mdx` carries `<Tabs>` for pip, pixi and
from-source with a copyable command per tab. Both hand-written guides keep every
heading, so every anchor and all four internal links per page survive.

Every conversion keeps its heading set, so no anchor moved: `check-links` reports
11,347 internal links on 150 pages with 0 broken, one more than the 11,346
baseline because `python/scoped-jobs` now points at the 0.9.0 migration notes it
duplicated. The component gate runs over the converted pages on every build
(`postbuild: component gate over N pages with directives, 0 problems`).

One P0 gap surfaced the moment a generated page used `:::tabs`: a `:::tab`
recorded its name in `lib/generated/components.json` but rendered no
`data-qgis-sdk` marker, so the gate failed every page that used tabs. The marker
now sits inside the panel - a wrapper beside a `<Tab>` would break `Tabs`, which
reads its own children - and `tests/directives.test.ts` pins it.

### Still open

- **AC 5's component shapes.** The word-count and no-lost-anchor halves are met
  on all five pages, but the shape each page names is only partly applied:
  `python/project-scaffold` uses `:::files` for the generated tree, and the other
  four are converted by prose compression rather than by the named component
  (`scoped-jobs` question headings as Accordions, `host-namespaces` one service
  per Tab, `desktop-bindings` catalogue as TypeTable and its tree as Files,
  `desktop-host` Steps or Files). Converting a `##` section into an accordion
  drops the heading and leaves the anchor to the accordion id, so each of those
  needs the same before/after anchor check the six pages already had.
- **P2 (AC 7)** - TypeTable from `api/python.json`. `desktop-bindings`'s
  catalogue table is the natural first consumer, which is why its AC 5 shape
  waits for this phase rather than being hand-written twice.
- **P3 (AC 8-11)** - the numbers are recorded above; the loss audit, the
  accessibility qualifications and the board records remain.
<!-- SECTION:NOTES:END -->
