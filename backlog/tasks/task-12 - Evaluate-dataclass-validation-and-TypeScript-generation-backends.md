---
id: TASK-12
title: Evaluate dataclass validation and TypeScript generation backends
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 15:10'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    backlog/decisions/decision-10 -
    Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
  - backlog/docs/plans/doc-5 - TASK-12-validation-backend-spike-evidence.md
priority: high
type: spike
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluate dataclass validation and TypeScript generation backends. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Compare apischema and TypeAdapter on strict requests, defaults/nullability, unions and separate input/output schemas.
- [x] #2 Exercise candidate Python/QGIS compatibility and generated TS/runtime-validator consistency.
- [x] #3 Record a recommendation and blockers under pure-Python-first packaging; native requirements need explicit reconsideration.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Run an isolated, pinned compatibility spike against ordinary dataclass request/result fixtures: compare apischema and Pydantic TypeAdapter strict decode, unknown fields, defaults/nullability/unions, separate input/output schemas and diagnostics; generate TypeScript from schemas and cross-check AJV runtime validators with shared positive/negative JSON fixtures; exercise Python/QGIS environments and record supported/untested targets plus pure-Python-first packaging, licensing and ABI tradeoffs. Keep candidates out of Pixi/Bun locks and production package; add reproducible focused tests and an evidence-based recommendation with blockers.

Subsequent user-directed durable example supersedes the earlier no-lockfile constraint only for development/test tooling: pin mashumaro, the Python JSON Schema oracle, Ajv, and json2ts in Pixi/Bun locks while leaving SDK runtime dependencies and backend selection unchanged.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed after user request. Public seam is dataclass DTOs -> Python validation/schema -> generated TypeScript/Ajv against shared JSON fixtures; experimental tooling only, no production backend selected. Existing TASK-11 changes remain untouched.

Pinned, isolated candidate probes and shared 25-case JSON oracle are in packages/qgis-sdk/tests/spikes; experimental schemas are checked snapshots and generated TS is kept in /tmp. apischema 0.19.0 and Pydantic TypeAdapter 2.14.1 each pass strict/default/null/union/output-schema and constraint/recursive probes. Python 3.14.8: 6 pass, 1 strict xfail for apischema dataclass without future annotations; supplemental Python 3.11.2: 7 pass; forced pure apischema wheel 3.11: 4 pass, 3 Pydantic skips. QGIS 4.2.3/Qt 6.11.2 Linux Python 3.14 co-import and candidate schema/decoding smoke passed. Ajv 8.20.0 checked 25/25 cases per backend; json-schema-to-typescript 16.0.0 and TS7 CLI generated and typechecked 2 contracts per backend. Root tests: 19 Python pass, 7 candidate skips, 2 bridge pass; separate coverage 100% both; Ruff/Biome/typecheck/PyPI build and Twine pass. Evidence, reproduction, limitations and recommendation to defer mandatory selection under pure-Python-first policy are in doc-5. Windows/Desktop/WebEngine and full environment integrity remain unverified. No dependency locks changed; no push/merge; leave task In Progress until landing.

2026-10-16 follow-up: added Hypothesis (80 examples/property/backend) for strict JSON request/default/result round-trips, plus two pytest-bdd scenario outlines across both candidates. Added test-only pinned hypothesis==6.169.4 and pytest-bdd==9.0.0 to isolated spike requirements, not runtime or Pixi/Bun locks. Extracted explicit pydantic_adapters configuration, shared test-only candidate adapter, and focused Ajv/codegen/tsc JS functions (solid-srp-function/core-dry). Isolated Python 3.14.8: 16 passed, 1 strict apischema eager-annotation xfail; Python 3.11.2: 17 passed; explicit pure apischema wheel 3.11: 9 passed, 8 Pydantic skips. Ajv remains 25/25 fixtures per backend, 2 deterministic TS outputs per backend typechecked. QGIS 4.2.3 Linux Python 3.14 co-import/schemas/decoding smoke passed. Root Python: 23 passed, 17 intentional candidate skips; 2 bridge passed (test cache replay), coverage 100% Python/bridge fresh; Ruff/Biome/typecheck/PyPI build+Twine/bridge build pass. Full root build blocked at Conda repodata access; no Conda package qualification. Report doc-5 updated with methods and limitations. No backend selected, lockfiles untouched; keep In Progress until landing.

2026-10-16 user-directed cleanup/review: removed the entire test-only packages/qgis-sdk/tests/spikes tree (DTOs, fixtures, snapshots, Python/BDD/Hypothesis probes, JS harness, isolated manifests). The original candidate checks in previous notes were executed before removal; doc-5 now labels them historical and not reproducible from this checkout. QGIS-free ResourceScope property/BDD tests remain. Compared requested generator alternatives with isolated Python 3.14.8 venvs, Python 3.11.2 supplemental for Latios, and TS7 strict checks: python-to-typescript-interfaces 0.2.0 requires Interface inheritance; ordinary DTOs emit nothing, modern Literal raises KeyError, str|None becomes UNKNOWN (TS2304). py-to-ts-interfaces 1.4.0 fails on the full DTO and emits invalid TS syntax (TS1005) for a standalone modern request, conflating nullable/defaulted. Latios96/py-typescript-generator v0.3.1 from a Git tag builds a pure wheel; plain dataclasses work for simple scalars, but Literal/PEP604 union fail, Python 3.14 Optional fails, and Python 3.11 output rejects valid null (TS2322). None provides strict Python request validation, separate input/output schemas or runtime frontend validators; none selected. Current checkout after removal: 23 Python tests passed with no candidate skips; 2 bridge tests passed via test cache replay, fresh coverage 100% Python/bridge, Ruff/Biome/typecheck/PyPI wheel+sdist/Twine passed. Full Conda build was previously blocked by repodata network access, not rerun. No dependency/lockfile changes, no push/merge; TASK-12 stays In Progress with its previously checked comparison criteria representing historical evidence, not persistent regression tests. Any production selection needs new durable contract tests.

2026-10-16 follow-up, user-directed durable example: added QGIS-free tests/contract_sample (not a restored spike) and root sdk:generate script. Mashumaro 3.23 exports three Draft 2020-12 sample schemas; locally pinned json2ts 16.0.0 generates checked TypeScript. A test-only Python jsonschema oracle and Ajv2020 8.20.0 agree on 24 shared fixed payloads for strict requests, explicitly allowed result-reader revision and default-complete writer; Hypothesis checks serialized results, five BDD scenarios check author behavior, and Python/TS tests reject stale generated bindings. Pixi/Bun locks now include development-only dependencies, including native rpds-py via test-only jsonschema; SDK runtime dependencies remain unchanged. Current Linux Python 3.14.8 root coverage: 55 Python and 30 bridge tests passed, both 100% measured production-source coverage; Ruff, Biome, TS typecheck and Pixi lock check passed. Mashumaro's default decoder still coerces/ignores extras, so no strict Python runtime backend has been selected. Earlier apischema/Pydantic evidence remains historical; QGIS/WebEngine/Windows, general SDK CLI and production runtime/backend are unresolved. No push/merge; keep TASK-12 In Progress.
<!-- SECTION:NOTES:END -->
