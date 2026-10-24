---
id: TASK-42
title: Refuse generated type names that collide with the emitter's own identifiers
status: Done
assignee: []
created_date: '2026-10-24 20:15'
updated_date: '2026-10-24 20:26'
labels: []
milestone: m-2
dependencies: []
priority: low
type: bug
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit finding (2026-10-24, post-merge audit of the generator). packages/qgis-sdk/src/qgis_sdk/bridge/generate.py:246-250 accepts any str.isidentifier() as a declared type name. Evidence: a description whose action sets result_name to isRecord generates 'export interface isRecord' next to 'function isRecord', producing TypeScript that fails tsc with a message that points at the validator body rather than at the manifest entry. Impact: the emitter's stated rule is to refuse what it cannot render instead of emitting a broken artifact; today a naming decision in a manifest fails one step later, in the consumer's build, with a message that does not name the cause. Intended behaviour: a declared name that is reserved by the emitter (its helpers, its exported surface constants and interfaces, and the shared boilerplate) or that is not a valid TypeScript identifier is refused with a QgisSdkBridgeError naming the type and the action. Non-goals: renaming generated helpers, and supporting namespaced type names.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _declared_name refuses the emitter's reserved identifiers (isRecord, hasOnly, isSafeInteger, call, InvokeOptions, BridgeClientLike, ContractError, PluginOperations, createOperations, OPERATIONS, OperationId and the host equivalents) with a QgisSdkBridgeError naming the type and its action.
- [x] #2 A declared name that is not a valid TypeScript identifier is refused with the same error shape.
- [x] #3 packages/qgis-sdk/tests/test_bridge_generate.py covers both refusals, and the checked-in artifacts still generate byte-identically so the drift check stays green.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (closed): `_declared_name` now refuses instead of silently falling back. It takes the action and the field so the message names both, rejects a non-string, a non-identifier (`"my type"`, `""`, `"gęś"`, `"1st"`, dotted paths) and a TypeScript keyword, then checks the identifier against `_RESERVED_NAMES` - every name the emitted module declares for itself, derived from both `_Surface` values plus the four validator helpers rather than from a copy that drifts. Before this, `result_name: "isRecord"` produced `export interface isRecord` beside `function isRecord`, which fails in the consumer build with a message pointing at a validator body. The fallback path is unchanged when the manifest names nothing, so both checked-in artifacts still regenerate byte-identically. Verification: 14 parametrised collisions (plugin and host surfaces), 5 non-identifiers, one keyword, one non-string, and the two artifact drift checks.
<!-- SECTION:NOTES:END -->
