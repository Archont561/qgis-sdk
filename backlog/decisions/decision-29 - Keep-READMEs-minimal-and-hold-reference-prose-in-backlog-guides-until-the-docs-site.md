---
id: decision-29
title: Keep READMEs minimal and hold reference prose in backlog guides until the docs site
date: '2026-10-24 21:20'
status: accepted
---
## Context

By 0.2.0 the three READMEs had become the project's only documentation:
`packages/qgis-sdk/README.md` ran to 870 lines and `README.md` to 130, each
task appending the section that proved its acceptance criteria. That shape has
three costs. A reader looking for "how do I install this" scrolls past
qualification matrices; the same prose is the PyPI and npm long description, so
every landing page carries harness JSON; and a README section is where evidence
goes to rot, because nothing checks it after the task that wrote it closes.

The owner asked for the opposite shape on 2026-10-24: READMEs the size of the
[pixi-sandbox](https://github.com/Archont561/pixi-sandbox) one or smaller, with
the detail held by the backlog and, later, by a documentation site in the style
of pixi-sandbox's Astro Starlight docs.

## Decision

1. **A README is a landing page.** Each one carries, in this order and nothing
   more: a one-line pitch, badges where the root has them, a status line naming
   the published version, installation, one short example, pointers to the
   guides, and the license. A section that explains, qualifies or records
   evidence does not belong in a README.
2. **Reference prose lives in backlog guides.** `backlog/docs/guides/` is a new
   taxonomy folder for `type: guide` documents that are documentation rather
   than plans or specifications:
   [doc-12](../docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md)
   (Python package),
   [doc-13](../docs/guides/doc-13%20-%20qgis-sdk-bridge-TypeScript-package-guide.md)
   (TypeScript bridge) and
   [doc-14](../docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)
   (workspace tooling, harnesses, qualification evidence). A task that lands a
   surface documents it there, in the section it belongs to, and cites the
   section from its notes.
3. **The docs site renders the guides.** [TASK-43](../tasks/task-43%20-%20Publish-a-Starlight-documentation-site-from-the-backlog-guides.md)
   owns an Astro Starlight site built from those guides. Until it ships, the
   guides are the readable source and the READMEs link to them on GitHub. When
   it ships, the README pointers move to the site and a check keeps the READMEs
   in shape 1.
4. **Nothing was dropped in the move.** Every section of the former READMEs
   is in one of the three guides under a heading that names the task or
   decision that wrote it, so the evidence trail that tasks 23, 24, 27, 28 and
   33 cite is intact. The scaffold's generated plugin README is a product
   output and is not covered by this decision.

## Consequences

- The PyPI and npm long descriptions become short landing pages; `release.yml`
  still packs `packages/qgis-sdk-bridge/README.md` into the npm artifact
  unchanged.
- `tests/scripts/test_backlog.py` already checks relative links across the
  backlog, so a guide that moves or renames is caught; the links the guides
  carry back to `AGENTS.md` and to each other are part of that check.
- Historical task notes that say "documented in the package README" now
  resolve to the matching guide section; the notes are not rewritten.
- Two things wait for TASK-43: a README-shape check, and the day the guides
  become site pages rather than backlog records.
