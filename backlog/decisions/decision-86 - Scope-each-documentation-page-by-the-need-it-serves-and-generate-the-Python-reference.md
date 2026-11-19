---
id: decision-86
title: Scope each documentation page by the need it serves, and generate the Python reference
date: '2026-11-19'
status: accepted
---
## Context

The site is organised by product: `python`, `typescript`, `contributing`,
`guides`, `reference`, `start`. Each page inside a product is organised by
topic. Measured on this branch, 108 pages hold 83,853 prose words, half of them
under `python/` at 913 words a page.

That second axis is the problem. A topic page is asked to answer four different
reader needs at once, and it answers them in one voice. The five pages converted
in TASK-170 P1 show it: `python/desktop-bindings-and-native-surfaces` was a
tutorial snippet, a how-to (wiring), a reference (an eleven-row component
catalogue with every option) and an explanation (why `@on` connects after
`build()`, decision-55) on one page, plus release prose. Cutting 25 percent off
those pages was possible because they were answering four questions, not because
the prose was bad. The next 25 percent is not there to cut: what remains is the
four answers, interleaved.

Diátaxis names the four needs - learning (tutorial), doing (how-to), looking up
(reference), understanding (explanation) - and asks for one of them per page. It
also asks the tree to follow the needs, which is the part this repository has
been getting wrong.

The reference quadrant has a second problem: provenance. `reference/api-index`
is 676 hand-committed table rows over `api/python.json`, so it is terse but it
can drift from the code, and every new stable name is a manual row.

Fumero settles the provenance half for Python: griffe reads an importable
module, the signature and defaults come from the source, the prose from the
docstrings, and the page cannot fall out of step with the code it documents.
Measured here before adopting it: 351 modules under `qgis_sdk`, 348 with a
docstring, **0** using `Args:`/`Returns:` and 0 using Sphinx field lists. So
generation today would render every signature correctly and every parameter
undescribed - which is exactly the work the reference needs and never got.

## Decision

1. **One page, one need.** Every page declares `kind: tutorial | how-to |
   reference | explanation` in its frontmatter, and belongs to exactly one. A
   page that needs to say something from another quadrant links to the page
   that owns it. The four kinds carry budgets: a tutorial ends at 1,200 prose
   words, a how-to at 700, a reference at 400 outside its tables, an
   explanation at 1,500.
2. **The budget is enforced as a ratchet, not as an aspiration.** The
   post-build gate fails on a page that exceeds the allowance recorded for it,
   and fails on a page that has fallen under its allowance without the
   allowance being lowered - the same shape as the clean-code budget
   (decision-80). No page is exempt; a page over its kind's budget carries a
   recorded allowance and a reason, and the allowance may only fall.
3. **The URL names the product, the page names the need.** `start/` is the
   tutorial surface, `guides/` and `<product>/how-to/` the how-to surface,
   `reference/` the reference surface, and `<product>/` the explanation
   surface. Where a page already carries a URL that is linked 11,000 times,
   the kind changes before the URL does: the frontmatter and the budgets come
   first, and a URL moves only where the page is genuinely split, with a
   redirect.
4. **The Python reference is generated, not maintained.** `fumero` (PyPI,
   pinned in the `python` feature of `pixi.toml`) reads the published surface
   and writes `content/docs/reference/python/`, which is gitignored like the
   rest of the generated content and rebuilt by the docs task. The
   hand-committed inventory keeps its two jobs - the per-tag diff and the
   freshness check (decision-85) - and `reference/api-index` keeps the coverage
   table; neither carries the member documentation any more.
5. **Docstrings are the prose, so they are held to the same standard.** A
   published name whose docstring documents no parameter is a reference page
   with rows and no descriptions. The docstring pass is part of this decision,
   not a follow-up: the published surface is documented in Google style, which
   is the dialect Fumero reads by default.
6. **TypeScript keeps its own answer.** Fumero reads Python only, and no
   equivalent generator is assumed for the TypeScript reference. Planning a
   symmetry that cannot be generated is how a reference drifts again.

## Consequences

- A page can be rejected in review for answering two needs, which was not
  previously sayable. The gate makes it a number rather than an opinion.
- The ratchet starts from the corpus as it is: pages over budget carry a
  recorded allowance, so the change lands green and each later conversion
  lowers one line.
- `content/docs/reference/python/` becomes a build product. A contributor
  running `bun run build` without the Python environment gets the hand-written
  reference pages and a reported gap rather than a silently missing section.
- The docstring pass touches the published modules and nothing else; an
  internal module stays undocumented, which the inventory already states by
  tier.
- Splitting a mixed page moves its anchor. The redirect table in
  `scripts/lib/redirects.ts` carries the old route, and `check-links` is the
  check that the move did not lose a reader.
