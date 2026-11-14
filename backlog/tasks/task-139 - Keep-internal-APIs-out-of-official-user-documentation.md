---
id: TASK-139
title: Keep internal APIs out of official user documentation
status: In Progress
assignee: []
created_date: '2026-10-28 16:43'
labels: []
dependencies: []
references:
  - apps/docs/guides
  - apps/docs/scripts/generate.ts
  - apps/docs/astro.config.ts
priority: medium
type: docs
ordinal: 139000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit the official documentation and generated reference sources for implementation-only APIs that leak into user-facing docs. Present only supported public SDK interfaces as the authoring API; keep contributor implementation guidance clearly separated rather than removing useful contributor material. Coordinate the public inventory and stability tiers planned in TASK-97. Do not treat undocumented internals as supported or remove exported behavior as part of this docs task. No release milestone is assigned.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Define and apply an explicit public-versus-internal documentation boundary across Python and TypeScript based on exports and intended support; identify ambiguous cases for review rather than assuming all exported names are public.
- [ ] #2 Remove or relocate internal modules and implementation-only APIs from user-facing guides and reference pages while retaining necessary public APIs and marking contributor-only documentation clearly.
- [x] #3 Fix the durable guide and generation sources so internals do not reappear on rebuild; preserve or redirect existing public links and do not break the contributor documentation.
- [x] #4 Add automated checks or an explicit reviewable allowlist to catch internal API leaks and cover the generated output; run documentation tests and a production build and link checks.
<!-- AC:END -->

## Implementation Notes

2026-10-28 (AC 1, 3 and 4 done; AC 2 left open on one decision):

- **The boundary is read from the inventory, not restated.** `api/python.json` - the document `release verify-api` diffs between releases - defines public: a Python name is public when its module is one of the 22 and its name is in that module's list; a TypeScript name is public when its subpath is in `packages/qgis-sdk-typescript/package.json`'s `exports`. Nothing in the documentation layer keeps a second list.
- **`tests/scripts/test_docs_boundary.py`** (8 tests) enforces it over the hand-written site, `README.md` and the two guide sources the site renders. Fenced code blocks are treated as templates - anything a reader copies must be a public name or be listed in `INTERNAL_IN_SNIPPETS` with its reason - while prose may name an internal, because the reference half of doc-12 explains where names moved and which adapter the framework calls on a reader's behalf. The allowlist has two entries, `qgis_sdk.adapters` and `qgis_sdk.bridge`, and an entry nothing reaches fails the suite.
- **Audit result (AC 2): no snippet leaked.** The only internal names in user-facing code blocks are `qgis_sdk.bridge.host` (registering the operations a web view calls) and `qgis_sdk.adapters.*` (bringing your own host, the server host, the app backend) - the two entries above. Every other internal reference is prose in doc-12's reference and changelog sections: `qgis_sdk.core.scheduling`, `qgis_sdk.core.scope`, `qgis_sdk.app._options`, `qgis_sdk.algorithms.algorithm`, the retired `qgis_sdk.hello`, and the note that `qgis_sdk.agent` is not part of the SDK.
- **AC 2 stays open on one decision**: whether the adapter and bridge reference sections move out of doc-12 into contributor documentation, or stay where a plugin author writing a custom host will look. Moving them would break the anchors those pages are linked by; leaving them is what the Stability section now says out loud.
- **The statement a reader meets**: doc-12 § Stability gained a paragraph saying these pages document the table's modules, that snippets import only those, that an internal may appear in prose and why, and that contributor material is doc-14. doc-13 § Exports gained the TypeScript half: the seven declared subpaths are the whole surface and the page imports only those.
