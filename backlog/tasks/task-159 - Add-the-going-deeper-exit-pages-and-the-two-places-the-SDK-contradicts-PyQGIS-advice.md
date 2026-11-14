---
id: TASK-159
title: Add the going-deeper exit pages and the two places the SDK contradicts PyQGIS advice
status: Done
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-10-28T21:00:00Z'
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
- [x] #1 doc-12 gains a "going deeper" page: when to leave the contract, the two exits (`ctx.desktop.iface` on Desktop, an adapter of your own) with the cost of each, and a link per unsupported area to the corresponding pyqgis.com hub - raster, layouts and atlas, symbology and labelling, attribute forms, custom classes, PostGIS and web services, temporal and 3D.
- [x] #2 The two contradictions are stated where a reader meets them, not in an appendix: the virtualenv/interpreter question on the installation and targets page, and mocking `iface` versus the fake-backed contract on the testing page - each saying what the corpus says, what this SDK does instead, and why.
- [x] #3 A troubleshooting page maps a symptom to a rule id and a fix, covering the thirty rule ids doc-12 already tabulates (dependency buckets, GUI state in a job body, a surface with no `objectName`, a stale generated client, an unqualified runtime pin), with the shortest reproducing example per entry.
- [x] #4 An IDE and typing page says what autocompletes today, what cannot (no PyQGIS stubs), and either links TASK-133's result or marks the section as pending it rather than promising it.
- [x] #5 A migration page takes a hand-written `initGui`/`unload` plugin of the classic shape to declarations, naming what is lost (`iface` breadth, arbitrary Qt widgets) and gained (fakes, grants, a generated page), with one before/after file pair.
- [x] #6 Every new page is reachable from the documentation index, the docs build passes, and no claim in them exceeds what the repository proves - no GUI or native evidence from the headless sandbox.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Source: `backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md` §6, which lists these gaps with the corpus hubs behind each. doc-12's current top level was read: it has sections for targets, the contract layer, forms, desktop bindings, grants and the console, the check rules (a table only), testing, dev, build and the per-version migration notes - and no troubleshooting, IDE, deployment or going-deeper page.

The rule table already exists in doc-12 (the thirty ids), so the troubleshooting page is a re-projection of text that is written, not new research.
2026-10-28, all six criteria. The five gaps doc-31 §6 named became three pages in
`doc-12` plus two additions where a reader actually meets the question.

- **AC 1 - going deeper.** `doc-12` § Going deeper: where this contract stops
  (`/python/going-deeper-where-this-contract-stops/`). Both exits are stated with
  their costs: `ctx.desktop.iface` (Desktop only, never serialised, no fake, so a
  test covering it needs a live QGIS) and an adapter of your own (implement a
  `qgis_sdk.services` Protocol and hand it to `host()`; you own both sides, and a
  shape a Protocol does not name stays out of reach). Then one row per
  unsupported area - attribute forms, custom classes, custom map tools, field
  management, PostGIS, web services, temporal and 3D, symbol-layer styling,
  memory layers, the pandas data stack, map-theme authoring, publishing - each
  with what the SDK does have and a link to the pyqgis.com hub that teaches the
  raw API. Every URL was read on the hub rather than guessed from a slug.
- **AC 2 - the two contradictions, where the reader meets them.** The
  virtualenv/interpreter question is in `doc-12` § Installation and linked from
  `apps/docs/content/docs/start/installation.mdx`; the `iface`-mocking question
  is in `doc-12` § Running tests and in `guides/test-a-plugin.md`. Each says what
  the corpus says, what the SDK does, and why. The site page carries the short
  form and points at the guide section, because decision-29 keeps one canonical
  explanation.
- **AC 3 - troubleshooting.** `doc-12` § Troubleshooting
  (`/python/troubleshooting/`): six symptom groups covering all thirty rule ids,
  one entry each with what `check` prints and the smallest repro. The repros were
  run - a scaffolded project, one mutation per rule, `check --json` asserting the
  id: 28 of 30 reproduced. The two that cannot be are stated as such: `HOST003`
  needs a visible QGIS without `qgis.server` (with no QGIS at all the state is
  unreadable, which is what this machine has), and `API001` needs a name carrying
  a mark, which no shipped name has.
- **AC 4 - IDE and typing.** `doc-12` § IDE, autocompletion and typing
  (`/python/ide-autocompletion-and-typing/`). Measured, not asserted: mypy
  reports `[import-untyped]` for `qgis_sdk` because no `py.typed` marker ships,
  and `[import-not-found]` for `qgis`; pyright 1.1.407 infers
  `Type of "app" is "QgisSdkPlugin"` from the installed source and fails only on
  `qgis.core`. The page says a `py.typed` marker is a decision about what the
  SDK's typing promises, marks it pending TASK-133, and promises nothing.
- **AC 5 - migration.** `guides/migrating-from/raw-pyqgis.md` already carried the
  mapping, the steps and a before/after pair; what it lacked was the trade, so it
  gained "What you lose, what you gain" - `iface` breadth and hand-written
  lifecycle against fakes, grants, a generated page and one description every
  tool reads.
- **AC 6 - reachable and proven.** The three `doc-12` sections become pages in
  the generated `/python/` index automatically; `guides/test-a-plugin.md` now
  ends with pointers to all three, `reference/faq.md` gained "Does the kit cover
  everything PyQGIS does?", and `start/installation.mdx` links the interpreter
  question. `next build` produced 108 routes with 0 unresolved, `check-links`
  resolved 10,861 internal links and fragments with 0 broken, and the docs suite
  passed 58 tests. No claim in the new pages rests on a GUI or native run: the
  contradictions, the typing table and the rule repros were produced on Linux
  x86-64 without QGIS, and where a claim would need QGIS the page says so.

**One documentation inaccuracy found and fixed.** The `META002` row in § Project
checks claimed `[project] name` was one of the keys the rule covers. It is not:
`metadata.txt`'s `name` is the application's declared `title` (or its id when
there is none), and removing `[project] name` from a scaffolded project produces
no finding. The row and the troubleshooting entry now name the four keys that are
actually checked. No rule changed.
2026-10-28, all six criteria. The five gaps doc-31 §6 named became three pages in
`doc-12` plus two additions where a reader actually meets the question.

- **AC 1 - going deeper.** `doc-12` § Going deeper: where this contract stops
  (`/python/going-deeper-where-this-contract-stops/`). Both exits are stated with
  their costs: `ctx.desktop.iface` (Desktop only, never serialised, no fake, so a
  test covering it needs a live QGIS) and an adapter of your own (implement a
  `qgis_sdk.services` Protocol and hand it to `host()`; you own both sides, and a
  shape a Protocol does not name stays out of reach). Then one row per
  unsupported area - attribute forms, custom classes, custom map tools, field
  management, PostGIS, web services, temporal and 3D, symbol-layer styling,
  memory layers, the pandas data stack, map-theme authoring, publishing - each
  with what the SDK does have and a link to the pyqgis.com hub that teaches the
  raw API, plus a paragraph for the three areas the contract does cover more
  narrowly (raster analysis, layouts and atlases, symbology and labelling).
  Every URL was read on the hub rather than guessed from a slug.
- **AC 2 - the two contradictions, where the reader meets them.** The
  virtualenv/interpreter question is in `doc-12` § Installation and linked from
  `apps/docs/content/docs/start/installation.mdx`; the `iface`-mocking question
  is in `doc-12` § Running tests and in `guides/test-a-plugin.md`. Each says what
  the corpus says, what the SDK does, and why. The site page carries the short
  form and points at the guide section, because decision-29 keeps one canonical
  explanation.
- **AC 3 - troubleshooting.** `doc-12` § Troubleshooting
  (`/python/troubleshooting/`): six symptom groups covering all thirty rule ids,
  one entry each with what `check` prints and the smallest repro. The repros were
  run - a scaffolded project, one mutation per rule, `check --json` asserting the
  id: 28 of 30 reproduced. The two that cannot be are stated as such: `HOST003`
  needs a visible QGIS without `qgis.server` (with no QGIS at all the state is
  unreadable, which is what this machine has), and `API001` needs a name carrying
  a mark, which no shipped name has.
- **AC 4 - IDE and typing.** `doc-12` § IDE, autocompletion and typing
  (`/python/ide-autocompletion-and-typing/`). Measured, not asserted: mypy
  reports `[import-untyped]` for `qgis_sdk` because no `py.typed` marker ships,
  and `[import-not-found]` for `qgis`; pyright 1.1.407 infers
  `Type of "app" is "QgisSdkPlugin"` from the installed source and fails only on
  `qgis.core`. The page says a `py.typed` marker is a decision about what the
  SDK's typing promises, marks it pending TASK-133, and promises nothing.
- **AC 5 - migration.** `guides/migrating-from/raw-pyqgis.md` already carried the
  mapping, the steps and a before/after pair; what it lacked was the trade, so it
  gained "What you lose, what you gain" - `iface` breadth and hand-written
  lifecycle against fakes, grants, a generated page and one description every
  tool reads.
- **AC 6 - reachable and proven.** The three `doc-12` sections become pages in
  the generated `/python/` index automatically; `guides/test-a-plugin.md` now
  ends with pointers to all three, `reference/faq.md` gained "Does the kit cover
  everything PyQGIS does?", and `start/installation.mdx` links the interpreter
  question. `next build` produced 108 routes with 0 unresolved, `check-links`
  resolved 10,862 internal links and fragments with 0 broken, and the docs suite
  passed 58 tests. No claim in the new pages rests on a GUI or native run: the
  contradictions, the typing table and the rule repros were produced on Linux
  x86-64 without QGIS, and where a claim would need QGIS the page says so.

**One documentation inaccuracy found and fixed.** The `META002` row in § Project
checks claimed `[project] name` was one of the keys the rule covers. It is not:
`metadata.txt`'s `name` is the application's declared `title` (or its id when
there is none), and removing `[project] name` from a scaffolded project produces
no finding. The row and the troubleshooting entry now name the four keys that are
actually checked. No rule changed.

**One stale status line found and fixed.** The guide's opening paragraph still
called `0.7.0` the released Python version and claimed the Python, bridge and UI
tags were cut on one merge commit. The tree publishes `0.11.0` beside bridge
`0.8.0`; TASK-95 records them on `f3fd460` and `592eb77` in separate runs, with
the Python release page and its missing artifacts being a known failure. The
paragraph now says that, and that `0.10.0` + `0.7.0` was the previous pair.
<!-- SECTION:NOTES:END -->
