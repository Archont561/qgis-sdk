---
id: TASK-120
title: Land and qualify the unified declaration describe API
status: Done
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Track the owner-approved unified API in decision-66: qgis_sdk.describe(target) and target.describe() share a dispatcher, including combined action and UI binding metadata. An implementation is included in the session work; the release and final qualification remain to be confirmed. Preserve old describe helpers and bridge serialization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both public entry points cover plugin, action, stream, job, algorithm, provider, surface and UI handler; action bindings and wires and plugin surface bindings are introspection-only and leave the serialized bridge unchanged.
- [x] #2 Preserve plain callable identity and legacy helpers, reject author-defined describe collisions with migration guidance, cover bound methods and inherited declarations, and document dynamic typing limitations and trusted annotation evaluation.
- [x] #3 Complete review, migration/release notes, full validation and actual merge/CI evidence before marking Done.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review and land the implementation, validate the declared supported kinds and collision migration, and record merge/CI evidence before closing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Local validation after Pydantic removal: 1897 Python tests passed, 47 skipped, 96.99% coverage; lint/format and TypeScript typecheck passed; earlier targeted QGIS Desktop built-plugin test passed for two independent vendored copies. This note records local validation only; it does not assert merge or CI status.
**Closed 2026-11-14: AC 3's merge and CI evidence now exists.** Both halves of
this task landed in PR #123, "feat!: unify introspection and refresh SDK
positioning", merged as `53e5198` on 2026-10-28 with its required checks green
(`checks`, `cross-platform` on macOS and Windows, `build and check the site`,
`lock guard`). The earlier note recorded local validation only; this one
records the merge.

Checked against the tree, not the notes: `describe()` in
`declarations/_describe.py` covers plugin, action, stream, job, algorithm,
provider and UI handler through one `_DESCRIBERS` table, and says in its own
docstring which parts are host metadata rather than bridge serialization; a
plugin *class* is refused with `QgisSdkDeclarationError` in favour of the
`QgisSdkPlugin`, actions and streams share one id namespace (decision-28), and
analysis never invokes a handler or a dataclass default factory.

**Documentation impact.** None: the guides and the generated contracts are
unchanged; this note records the merge.
<!-- SECTION:NOTES:END -->
