---
id: TASK-40
title: Refuse a malformed paging cursor instead of restarting the first page
status: Done
assignee: []
created_date: '2026-10-24 20:14'
updated_date: '2026-10-24 20:26'
labels: []
milestone: m-2
dependencies: []
priority: high
type: bug
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit finding (2026-10-24, post-merge audit of the host surface). packages/qgis-sdk-python/src/qgis_sdk/bridge/host.py:291-296 parses the paging cursor with int() inside a try, falls back to 0 on ValueError, then clamps with max(start, 0). Evidence: layers.list with {"cursor": "abc"} returns the first page, {"cursor": "-3"} returns the first page, and {"cursor": "2.7"} returns the first page. Impact: a page that persists next_cursor and resumes later can silently restart at offset 0 and loop forever against a host that keeps answering truthfully; the failure looks like a client bug because the host never says anything. Intended behaviour: a cursor that is not a non-negative decimal integer is refused before the service method runs, an absent cursor still means the first page, and a cursor the host issued still resumes at its offset. Non-goals: keyset cursors, changing DEFAULT_PAGE/MAX_PAGE, and paging Layers.selection (still deferred to its own task).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 layers.list and project.layer_ids refuse cursor values that are not non-negative decimal integers ("abc", "-1", "2.7", " 2") with a stable error code naming the cursor field.
- [x] #2 An absent cursor still returns the first page and a host-issued cursor still resumes at its offset.
- [x] #3 packages/qgis-sdk-python/tests/test_bridge_host.py covers each malformed form at the dispatcher seam and asserts the service method was never called.
- [x] #4 The constraint is expressed in the schema subset so the generated client refuses the same cursor before the transport, or the task notes record why the check is host-only.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (closed): the cursor is now a declared shape, not a handler convention. `PAGE_REQUEST.cursor` carries `pattern: "[0-9]+"`, which needed `pattern` in the closed subset on both sides: `qgis_sdk.bridge.schema` matches with `re.fullmatch` (anchors are never required) and the generator emits `new RegExp("^(?:...)$")`, so the two agree on "the whole value". A malformed cursor is therefore refused by `_input_refusal` with `invalid_payload` and the field path, before the wrapped Protocol method runs - `_offset` is now the `int()` the schema already earned, and the "read a bad cursor as start over" path is gone. The host fingerprint moved with the contract change (`sha256:851a7738...`), which is what it is for; `HOST_SCHEMA_VERSION` and `BRIDGE_PROTOCOL_VERSION` stay 1 because nothing about the envelope moved. Widening the subset is itself a contract change, recorded here rather than in a decision because it closes a defect: `test_a_declared_string_pattern_matches_the_whole_value` pins the host, `test_a_declared_string_pattern_is_emitted_as_a_whole_string_test` and the generated `PageRequest` case in `packages/qgis-sdk-typescript/tests/host.test.ts` pin the client. Also fixed on the way: `src/host.ts` re-exported the page and layer interfaces as `type` only, so a page could import the validator names in a type position and get nothing at runtime - every name with a generated validator is now a value export. Verification: 724 Python tests (1 pre-existing sandbox-only failure in `test_pure_imports.py`: the isolated interpreter cannot see `~/.local`), 135 TypeScript tests, `tsc --noEmit` clean, biome clean, both generated artifacts regenerate byte-identically.
<!-- SECTION:NOTES:END -->
