---
id: TASK-108
title: >-
  Adopt the declarative surface form across the scaffold, the web mirror and the
  snapshot tooling
status: Done
assignee: []
created_date: '2026-10-27 10:02'
updated_date: '2026-10-27 14:55'
labels:
  - ui
  - python
milestone: m-6
dependencies:
  - TASK-96
  - TASK-70
type: feature
ordinal: 108000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-96's pull request (PR #105) added the declarative form of a surface as a decision-55 amendment: components assigned to class attributes take the attribute's name, the default `build()` returns the declared roots, `@on(component)` wires to that window's copy, and every opening deep-copies the declared set (`qgis_sdk.ui.declarative`). The runtime, the fake rendering, `check` (UI002 leaves component targets to the host) and the example's `ResultsDock` already use it; doc-12 documents it.

What is left is adoption and the places that read a surface statically:

- the scaffold's `PingDialog` (`qgis-sdk new --ui native`) and its README show the imperative `build()` form only; decide whether the starter declares its components (the example shows both forms on purpose: `BufferDialog` builds because its `Form` needs `ctx`);
- `qgis-sdk check` could read declared components statically (an `@on(clear)` whose attribute is not a component; a declared `Custom(widget=<instance>)`, which fails only when the window opens) - today both are host-time refusals;
- the web mirror of the catalogue (TASK-70) should offer the same keyword forms so a component reads the same in Python and TypeScript;
- `Form` still keys its inputs by name at construction, so inputs declared on the class cannot be grouped in a `Form` without naming them; decide whether `Form` resolves field names lazily like `Container`;
- the UI snapshot of a declared surface (decision-51, TASK-79) could carry the attribute names next to the object names, which is what an agent reads back.

Not in scope: changing the imperative form or the positional constructors, which stay.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The scaffold's native starter and its README either declare their components or say in one sentence why they build; the scaffold-desktop harness stays green.
- [x] #2 `qgis-sdk check` reports a declared `Custom` holding a widget instance and an `@on(<attribute>)` whose attribute is not a component, statically, with tests.
- [x] #3 `Form` accepts inputs declared on the surface class (names resolved when the form is attached), or doc-12 states that `Form` fields are always named and why.
- [x] #4 The web catalogue (TASK-70) takes the same keyword forms as the Python one for the shared component names; the mirror table in doc-13 lists both spellings.
- [x] #5 doc-12 and decision-55's status review reflect the outcome; the example and the scaffold do not diverge.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Merged in PR #108 (6efc4fc), CI green on main. Scaffold PingDialog declared; UI005 in check; Form over declared inputs + initial seeding + snapshot attribute; web keyword forms (options/required/cancellable/text/of) with ELEMENT_PROPS test; doc-12/doc-13 mirror table/decision-55 status review. Known sandbox-only devtools vite deadline failure reproduced on baseline, CI passed.
<!-- SECTION:NOTES:END -->
