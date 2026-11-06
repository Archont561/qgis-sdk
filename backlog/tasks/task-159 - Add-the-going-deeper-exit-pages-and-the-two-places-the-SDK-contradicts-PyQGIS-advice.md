---
id: TASK-159
title: Add the going-deeper exit pages and the two places the SDK contradicts PyQGIS advice
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - apps/docs/guides/doc-12 - qgis-sdk-Python-package-guide.md
  - backlog/tasks/task-135 - Show-the-end-to-end-one-action-plugin-authoring-story.md
  - backlog/tasks/task-138 - Make-official-documentation-concise-and-visually-guided.md
  - backlog/tasks/task-139 - Keep-internal-APIs-out-of-official-user-documentation.md
priority: medium
type: docs
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
doc-12 is a good reference for what the SDK does and a poor guide for a reader who arrives from the PyQGIS corpus (doc-31 §6). Four things are missing: a signpost for the large areas the contract will never cover, the two places where the SDK deliberately contradicts advice the corpus gives, a page that turns a `check` rule id into a fix, and a narrative for migrating an existing hand-written plugin.

The two contradictions matter most, because a reader who follows the corpus inside an SDK project gets a worse result: "do not use a virtualenv, use QGIS's interpreter" is wrong for a plugin built and vendored by `qgis-sdk build`, and "mock `iface` in tests" is precisely the practice the fake-backed contract replaces.

Documentation-only proposal: no milestone, no release. Kept separate from TASK-135 (the one-action authoring story), TASK-138 (concision and visual guidance) and TASK-139 (keeping internal APIs out), so those three do not absorb it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 doc-12 gains a "going deeper" page: when to leave the contract, the two exits (`ctx.desktop.iface` on Desktop, an adapter of your own) with the cost of each, and a link per unsupported area to the corresponding pyqgis.com hub - raster, layouts and atlas, symbology and labelling, attribute forms, custom classes, PostGIS and web services, temporal and 3D.
- [ ] #2 The two contradictions are stated where a reader meets them, not in an appendix: the virtualenv/interpreter question on the installation and targets page, and mocking `iface` versus the fake-backed contract on the testing page - each saying what the corpus says, what this SDK does instead, and why.
- [ ] #3 A troubleshooting page maps a symptom to a rule id and a fix, covering the thirty rule ids doc-12 already tabulates (dependency buckets, GUI state in a job body, a surface with no `objectName`, a stale generated client, an unqualified runtime pin), with the shortest reproducing example per entry.
- [ ] #4 An IDE and typing page says what autocompletes today, what cannot (no PyQGIS stubs), and either links TASK-133's result or marks the section as pending it rather than promising it.
- [ ] #5 A migration page takes a hand-written `initGui`/`unload` plugin of the classic shape to declarations, naming what is lost (`iface` breadth, arbitrary Qt widgets) and gained (fakes, grants, a generated page), with one before/after file pair.
- [ ] #6 Every new page is reachable from the documentation index, the docs build passes, and no claim in them exceeds what the repository proves - no GUI or native evidence from the headless sandbox.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Source: `backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md` §6, which lists these gaps with the corpus hubs behind each. doc-12's current top level was read: it has sections for targets, the contract layer, forms, desktop bindings, grants and the console, the check rules (a table only), testing, dev, build and the per-version migration notes - and no troubleshooting, IDE, deployment or going-deeper page.

The rule table already exists in doc-12 (the thirty ids), so the troubleshooting page is a re-projection of text that is written, not new research.
<!-- SECTION:NOTES:END -->
