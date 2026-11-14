---
id: TASK-121
title: Land and qualify removal of the Pydantic controlled deployment adapter
status: Done
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: medium
type: chore
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Track the owner-requested retirement in decision-67. The session implementation removes qgis_sdk.adapters.pydantic, pydantic_types, controlled-deployment extras and adapter-specific fixtures, generation, tests and qualification. Do not block plugins from using separately provisioned Pydantic; no new SDK installation policy is implied.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Runtime and kit wheels no longer contain the adapter or expose the controlled-deployment extra; development dependency and obsolete SDK-specific generated artifacts are removed without affecting supported ordinary contracts.
- [x] #2 Release tooling, lockfile, supported contract generation and documentation pass; migration notes state there is no drop-in replacement and the change ships in a Python minor, not a patch.
- [x] #3 Record actual review, merge and CI evidence before marking Done.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review and land the breaking removal in a future Python minor with migration notes and evidence, preserving historical release records.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Local checks after removal: 1897 Python tests passed and 47 skipped with 96.99% coverage; 262 release-tool tests passed, Pixi lock check, normal contract generation, TypeScript typecheck, docs build/link check and local wheel inspections passed. This note records local validation only; it does not assert merge or CI status.
**Closed 2026-11-14: AC 3's merge and CI evidence now exists.** The removal
landed in PR #123, merged as `53e5198` on 2026-10-28, with the required checks
green. The earlier note recorded local validation only; this one records the
merge.

Checked against the tree: `packages/qgis-sdk-runtime/pyproject.toml` declares
`dependencies = []` and no controlled-deployment extra, no `pydantic` import
remains anywhere under `packages/` (the only mentions are the two comments in
`automation/` explaining why gherlint pins pydantic 1 in a throwaway
environment), and no deployment adapter file exists. The kit's extras are
`mcp` and `dev`, nothing else. The migration notes state that there is no
drop-in replacement and that the change ships in a Python minor - 0.11.0, one
minor after it landed.

**Documentation impact.** None: the guides were updated in the same pull
request; this note records the merge.
<!-- SECTION:NOTES:END -->
