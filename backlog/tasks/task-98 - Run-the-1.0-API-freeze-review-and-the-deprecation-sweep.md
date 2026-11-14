---
id: TASK-98
title: Run the 1.0 API freeze review and the deprecation sweep
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-97
type: task
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-56 point 5. Review every stable symbol against the inventory: remove or mark every pre-1.0 leftover (require_<name>(), NativeForms aliases, old error names), settle naming inconsistencies in one documented minor, confirm doc-22 complete or out of scope by decision, and write the 1.0 migration notes. Output is a reviewed inventory, not new features.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No stable symbol is undocumented, every deprecated symbol has a removal version at or after 1.0, and verify-api between the last 0.x tag and the review commit lists only classified changes.
- [ ] #2 doc-22 shows every row complete or out of scope by decision with a link; doc-12 carries the 1.0 migration notes and the stability policy in the owner's words.
- [ ] #3 A reviewed inventory is committed as the baseline verify-api diffs against after 1.0.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-28, AC 1 and 3 measured and their first half shipped; AC 2 and the
review itself remain. This is a review task, not a feature, so the note records
what the audit found rather than claiming the freeze.

**AC 1, "no stable symbol is undocumented" - now enforced, not asserted.** The
audit before this slice found **201 of the 632 stable names appearing on no page
at all**: 67 in `qgis_sdk.models`, 34 in `qgis_sdk.declarations`, 19 in
`qgis_sdk.services`, the rest across `bindings`, `ui`, `app`, `jobs`, `core`,
`network`, `server`, `testing`, `environment`, `batch`, `exports`, `algorithms`,
`console`, `deprecation` and `processing`. The cause was structural rather than
careless: the guide names the class a reader uses and not the wire constant, the
protocol or the error beside it, and nothing failed when a name was added.

The fix is `reference/api-index`: one section per public module and one row per
name with the shape `api/python.json` records, rendered by
`apps/docs/scripts/lib/api-index.ts` on every build. The inventory is the only
source of names, so coverage is total by construction and cannot drift - a name
the code adds appears, a name it drops disappears. `apps/docs/tests/api-index.test.ts`
(9 tests) holds the edges: every module has a note in `scripts/api-modules.ts`,
every note's heading still exists in the guide it names (so a renamed section
breaks the suite instead of the site), a pipe in a signature cannot end its cell,
a name with no signature prints as `class` rather than an empty cell, and the
counts of the surfaces the page does not list come from the document rather than
from prose.

**What is still prose-free is recorded here rather than hidden.** The 201 names
now appear only on the index. That is "documented" in the sense of "a reader can
find out that it exists, what it takes and what tier it carries"; it is not
"somebody explained it". The largest cluster is `qgis_sdk.models`' wire constants
(`CATEGORIZED_RENDERER`, `BLOB_REF`, the `*_from_wire` readers), which the guide
describes behaviourally without naming. Reading the index page is how the owner
decides which of those earn a paragraph; the page also names its own gap, saying
"No guide section introduces this module yet" for the one module whose narrative
is missing (`qgis_sdk.exports`).

**AC 1, deprecation window: vacuous, and it stays that way until something is
marked.** `api/python.json` records `"deprecations": []`. `NativeForms`,
`DeclaredFormDialog`, `qgis_sdk.hello` and the `require_<name>()` helpers the
description names were removed in the 0.x minors, so there is nothing to give a
window to and `check` has no `API001` finding to make. The index page states that
rather than implying the rule has teeth today.

**AC 1, "verify-api between the last 0.x tag and the review commit": cannot
run.** `release verify-api --tag python-v0.11.0` answers "python-v0.11.0 records
no `api/python.json`; the first tag that carries one is the first that can be
diffed" - the inventory entered the tree after that tag (TASK-97). The first
diffable baseline is therefore this tree, which is AC 3 rather than a gap.

**AC 2, the doc-22 half: the map is now gated against the board, and two rows
were wrong.** `test_backlog.py` gained three tests: a row in *Planned* or
*Proposals awaiting a decision* whose own task is Done fails, every task id the
map cites must exist, and the map's tables are read as data rather than by eye.
Writing the gate found the drift it was written for - [TASK-159] sat in
*Proposals awaiting a decision* after it shipped - and two smaller errors: the
safety warning still called TASK-118 and TASK-119 "known data-safety gaps" a
release after both were fixed and merged (the paragraph now says what the
fail-closed policy guarantees and which three limits remain outside it), and the
Jobs row still described worker-first jobs as "planned for 0.9.0" when
TASK-115-117 are Done. What stays open in the map is genuine: two 1.0.0 areas
(`ctx.log` and i18n) are planned with open tasks, and ten PyQGIS-corpus
proposals await a decision. "Every row complete or out of scope by decision" is
therefore still not true, and it will not be until those twelve rows move - the
gate now makes sure none of them moves by accident or stays after it has.

**AC 2, the 1.0 migration notes: open, and they belong to the release.** A
1.0 migration note written before the sweep would describe a set of names
the sweep has not chosen yet.

**AC 3, the reviewed inventory: present.** `api/python.json` (22 modules, 632
names, 25 rules, 84 host operations, 127 CLI entries, `API_VERSION` 1) is
committed, regenerated by `qgis-sdk api dump`, and
`tests/scripts/test_api_inventory.py` fails when it no longer describes the tree.
The new page is the human-readable form of the same document, so the review this
criterion asks for can be done by reading one page rather than four thousand
lines of JSON.
<!-- SECTION:NOTES:END -->
