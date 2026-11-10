---
id: decision-78
title: Tighten the reference pages, answer the adoption questions in one FAQ, and fetch registry numbers at build time
date: '2026-11-10'
status: accepted
---
## Context

The site had a reference that explained itself well and no page a prospective
adopter reads first. The reference pages answered "which limits apply?" with a
paragraph whose first sentence was about where the numbers came from ("Defaults
from measurement"), then the numbers; the networking page listed ten error
classes in running prose. A reader deciding whether to adopt had nowhere to ask
"does it work with QGIS 4", and an agent operator had nothing to paste into a
repository.

Three kinds of page were missing, and each raised the same question: where does it
live, given that `/python/`, `/typescript/`, `/contributing/` and most of
`/reference/` are rendered from the guides and the backlog by
`scripts/generate.ts`?

## Decision

1. **The tightening rules are: fact first, repeated shapes as tables, cards
   short.** A limit, a default or a constraint is the first sentence; the
   justification follows it. An error catalogue, a grant list or a set of
   defaults becomes a table with one row per item. A card or a hero lead carries
   one idea per sentence and stops. Applied to the networking section of doc-12
   (the numbers now open the paragraph; the ten network errors are a table with
   their `code` strings) and to the landing page hero.
2. **Headings are not renamed to satisfy the rules.** `apps/docs/tests/sources.test.ts`
   holds every anchor in the historical `backlog/docs/guides/` stubs to the
   current source, and those anchors are how older documents link. The prose
   under `Defaults from measurement` changed; the heading did not.
3. **The FAQ is hand-written inside a generated folder.**
   `content/docs/reference/faq.md` is in git; `generate.ts` replaces
   `design-decisions.mdx` and the folder's `meta.json` individually rather than
   removing the directory. It is the only mixed folder, and the generator's
   docstring says so. The alternative - a `pages/` source tree the generator
   copies - adds a second place a page can come from for one page.
4. **Migration pages are guides, one per previous world** (`raw-pyqgis`,
   `plugin-builder`), each an artifact-to-declaration table, a numbered port, one
   paired before/after and gotchas that name the check code that enforces them.
   They describe moving *code*, not the release history the `migration/` notes
   describe.
5. **The roadmap names no dates and no versions it has not shipped.**
   `roadmap.mdx` has four cards - now, next, shipped, considering - and the
   version line is the component reading `lib/generated/versions.json`, so it
   moves with the tree instead of being edited. Release candidates are called
   candidates on the card, because the tree is ahead of the last stable cut.
6. **Registry numbers are fetched at build time and never block a build.**
   `scripts/lib/stats.ts` asks PyPI and npm for last-month downloads while
   `generate.ts` runs, writes `lib/generated/stats.json`, and turns every
   failure, timeout (4 s) or unexpected shape into `null`; the install page
   renders a dash for those rows. `STATS_OFFLINE=1` skips the requests. Nothing
   is committed, so a stale number cannot outlive its release.
7. **The examples gallery waits for three examples.** `examples/simple` stays the
   walkthrough inside Quick Start; a card grid over one project is a page that
   says "more coming".

## Alternatives considered

- **Commit a `stats.json` from a nightly workflow** (the shape this kind of page
  usually has). Rejected: it is data with an owner nobody remembers, it goes
  stale between runs, and it needs a bot commit on a schedule for four numbers -
  a build-time fetch with a dash fallback has neither failure mode.
- **A third-party badge per registry** (shields-style images). Rejected: an
  image that a third party serves is a request to that third party on every page
  view, and it fails to a broken image rather than to a dash.
- **A "For agents" sidebar badge via Fumadocs' status plugin.** Rejected for now:
  the plugin reads a `status` field the page schema strips, so widening the
  schema means adding `zod` as a direct dependency of the docs app and a lockfile
  change, for one label. The page is discoverable by title and by the Guides
  section.
- **Starlight components** (`CardGrid`, `template: splash`). Not applicable: the
  site is Fumadocs with `output: "export"`, so the roadmap uses `Card`/`Cards`
  and the cards are server-rendered with the rest of the page.

## Consequences

- Three new page classes are served by the existing pipeline: nothing was added
  to the sitemap, the llms trio or the `.md` export logic, and the route count
  went from 99 to 104.
- The install page is now `installation.mdx`, because it hosts a component; the
  route is unchanged.
- A build makes two outbound requests it did not make before, with a 4 s ceiling
  each and a dash on failure. An offline build still succeeds.
- `reference/` is the one folder where a hand-written page and a generated page
  live together; the generator's docstring records the exception so the next
  person does not "fix" it by removing the folder.
