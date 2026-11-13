---
id: TASK-164
title: Add the FAQ, migration paths, agent onboarding, roadmap and registry stats to the site
status: Done
assignee: []
created_date: '2026-11-10 09:10'
updated_date: '2026-11-13 09:15'
labels: []
dependencies: []
ordinal: 164000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The reference explains the SDK and nothing answers the adoption questions. Tighten the reference pages (fact first, repeated shapes as tables, short leads), add an FAQ, two migration guides, a page for coding agents, a roadmap without dates, and the registry download counts on the install page - all through the existing Fumadocs pipeline, with no new dependency and no build that fails when a registry API is down.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The networking section of doc-12 opens with the limits and lists the ten network errors as a table with their code strings; no heading loses its historical anchor.
- [x] #2 The landing page hero lead is three short sentences, one idea each.
- [x] #3 /reference/faq/ answers the eight adoption questions, each answer at most four lines and ending in one canonical link.
- [x] #4 /guides/migrating-from/plugin-builder and /guides/migrating-from/raw-pyqgis map artifacts to declarations, then give a numbered port, one before/after pair and gotchas that name their check codes.
- [x] #5 /guides/for-agents/ carries a copyable AGENTS.md block and the scaffold-check-test-build loop.
- [x] #6 /roadmap carries no dates, calls the 0.11 and 0.8 lines candidates, and reads the version line from the generated versions rather than from prose.
- [x] #7 The install page tables the registry counts; a registry that does not answer renders a dash and the build still succeeds.
- [x] #8 The examples gallery is still not a page: the single reference project remains the Quick Start walkthrough.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision-78 records the choices and the four alternatives rejected. The generator owns `reference/design-decisions.mdx` only, so the hand-written `reference/faq.md` survives a regenerate; `bun test` in `apps/docs` holds the historical anchors, and `check-links` resolved 10,068 internal links with none broken.
<!-- SECTION:NOTES:END -->
