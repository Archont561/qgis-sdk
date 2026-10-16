---
id: decision-22
title: Use strict inputs extensible results and experimental contracts
date: '2026-10-16 09:05'
status: accepted
---
## Context

Strict validation must coexist with the accepted versioned additive compatibility direction. Errors and generated bindings need consistent author/frontend behavior before stable 1.0 commitments.

## Decision

Reject unknown request fields and avoid implicit type coercion by default. Numeric strings and booleans-as-integers are not accepted merely because a backend can convert them. Any supported conversion must be explicit. Define required/defaulted/nullable distinctions and preserve them across Python/TS schemas. The validation-backend spike must test these rules.

Response readers validate required known fields and their types while tolerating only additions explicitly classified as compatible. Do not apply unknown-request-field rejection blindly to extensible result objects. Missing required results, changed types, incompatible unions and unsupported protocol versions still fail. Adding an optional request field is compatible only in a direction where old hosts are not sent unsupported fields. Exact operation/event/envelope compatibility rules remain to be implemented and tested; permissive arbitrary extras are not the policy.

Python handlers raise stable typed SDK/domain errors for expected failures; the bridge translates them to structured codes/details. Unexpected exceptions retain full host diagnostics with correlation IDs but expose safe user/frontend failures, not paths/secrets/internal traces. Detailed developer diagnostics are explicit and redacted; do not send tracebacks indiscriminately to web views. Standard Promise rejection remains untyped; a future Result helper is not selected here.

Check generated TypeScript contracts into plugin projects, mark ownership clearly and enforce deterministic generation/drift checks in CI. This supports review and frontend work without a running QGIS. Generation still requires a consistent Python schema toolchain when rerun.

Initial public releases are experimental 0.x with breaking-change/migration notes; the v1 product milestone does not mean an immediate stable 1.0 API. Keep protocol compatibility/versioning distinct from package versions. If the Qt-compatible coroutine spike fails cancellation/cleanup/Windows/Linux criteria, explicitly revisit scope with the user: neither silently downgrade nor assume a preauthorized release-blocking/fallback choice.

## Consequences

- Spikes and contract tests must validate strictness and asymmetric compatibility independently on both sides.
- A future stable API/deprecation policy requires another explicit decision after reference workflow and runtime qualification.
- Exact diagnostic schemas, compatibility algorithm and async implementation remain open; acceptance is not implementation evidence.
