---
id: doc-3
title: Reference workflow and runtime safety acceptance
type: specification
created_date: '2026-10-16 09:05'
updated_date: '2026-10-16 09:05'
---
# Reference workflow and runtime safety acceptance

**Status:** Confirmed policy from the second 2026-10-16 interview, not implemented behavior. Initial releases are experimental 0.x; public names, numeric limits and mechanisms remain open. This complements the product and web bridge specifications.

## 1. Observable reference workflow

Load a local vector dataset, inspect selected features, run one distance-based Processing operation with explicit projected working CRS/units, and style a new output. Expose equivalent native and web controls (vanilla/React, dialogs/docks). Do not depend on a live external catalogue for this reference. Use deterministic networking fixtures and a controlled separate native networking test.

Preserve source data. On success, finalize a new temporary output and add it to the project on the GUI thread. On failure or acknowledged cancellation, clean incomplete temporary output and do not present it as a completed project layer. Permanent exports require explicit destination/overwrite authority and defined partial-file cleanup. The operation, licensed dataset, style and transformation UI remain choices to qualify.

## 2. Boundary behavior

| Situation | Required observable result |
| --- | --- |
| Geographic/ambiguous distance units | Reject or request explicit working CRS/units/transformation; never silently interpret degrees as metres |
| Invalid/extra request field or implicit conversion | Structured validation failure; handler not called |
| Removed layer or stale/foreign handle | Explicit typed failure; never find another layer by name |
| Missing file grant | Reject before file access; path text alone is not authority |
| Disallowed host URL/method/auth/redirect | Reject according to per-view constraints, without leaking credentials |
| Browser navigation/resource request outside policy | Enforce qualified browser restrictions separately from host HTTP rules |
| Expected domain failure | Stable code and safe details; no invented success |
| Unexpected exception | Safe frontend message/correlation ID and full redacted host diagnostics |
| Compatible additional result field | Validate known fields and tolerate only additions allowed by protocol policy |
| Missing/changed required result field | Contract error, not unchecked TypeScript casting |

## 3. Owned work and refresh

View-submitted jobs are view-owned by default. Hiding a dock preserves its lifetime; disposing a view detaches callbacks immediately and requests cancellation. Plugin-lifetime jobs require explicit ownership and cannot retain disposed widgets. Initial jobs omit automatic retries. Do not treat cancellation requested as acknowledged terminal state.

Reload preflight failures preserve the running revision. Once quiesced, wait for safe completion within a bounded policy. If code/native resources remain active, refuse in-process reload and require explicit restart; do not kill threads or unload beneath them. Old-generation guards prevent delivery but are not proof of cleanup. Define unsaved-state handling before process restart.

## 4. Tests and qualification outcomes

Use examples, properties/state machines and behavioral scenarios at their actual runtime boundary:

- Given source data and selected features, successful execution creates exactly the expected new output, preserves source and styles/adds output only after success.
- Given invalid distance/CRS/input, the handler is not invoked and diagnostics are actionable.
- Given failure/cancellation, incomplete temporary resources are released and no success result is delivered.
- Given disposed view, old progress/completion cannot update it; hidden docks remain valid.
- Given cancellation that never safely completes, reload is refused with the identified blocker.
- Given stale/foreign handle, denied file grant or restricted network target, no privileged effect occurs.
- Given an external browser resource/navigation attempt, test the real WebEngine policy; a fake transport is not security evidence.
- Given compatible/incompatible schema changes, Python and TS agree on the defined result and preserve strict requests.
- Given regenerated bindings, CI detects drift without hand-maintained duplicate interfaces.

Pure harnesses prove dispatch/ownership contracts. Real QGIS tests prove Processing/geometry/project/native behavior; actual QWebEngine tests prove bridge/browser enforcement. Qualify selected QGIS 4 Windows/Linux x86-64 builds explicitly. The workspace pin or passing smoke tests does not establish support.

## 5. Explicit open engineering work

Choose exact reference algorithm/dataset/style, supported build matrix, resource grant representation/revocation, browser enforcement, timeout/body/concurrency limits, scheduler and compatibility algorithm. The dataclass spike must test strict/coercive distinctions and input/output schemas under the accepted pure-Python-first packaging policy. If async qualification fails, revisit scope explicitly; no silent downgrade is authorized. Stable 1.0/deprecation guarantees are later decisions, with migration notes for experimental 0.x changes.

## Related decisions

- [decision-17](../../decisions/decision-17%20-%20Deliver-a-qualified-Python-first-vertical-slice-for-v1.md)
- [decision-19](../../decisions/decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md)
- [decision-20](../../decisions/decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md)
- [decision-21](../../decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md)
- [decision-22](../../decisions/decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md)
