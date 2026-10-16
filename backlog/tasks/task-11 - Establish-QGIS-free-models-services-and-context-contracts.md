---
id: TASK-11
title: Establish QGIS free models services and context contracts
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 14:16'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-14 -
    Enforce-QGIS-free-import-boundaries-during-check.md
priority: medium
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Establish QGIS free models services and context contracts. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Enforce models/services/core dependency direction and native-import isolation with pure import tests.
- [x] #2 Specify plugin/UI/algorithm/job scoped typed contexts and fake-service seams without global registration.
- [x] #3 Document typed errors, lifecycle ownership and explicit unsupported/native capabilities.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement the m-0 QGIS-free contract slice in vertical TDD cycles: expose typed model/error and narrow service contracts; compose explicit plugin, UI, algorithm and job contexts with scope ownership and unsupported native capability semantics; prove imports and dependency direction with pure/subprocess tests; document supported seams and deliberately deferred QGIS adapters. Validate with focused and root tests, coverage, lint and build where applicable.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed after user approval; confirming public test seams before tests per TDD skill. No implementation or acceptance criteria claimed yet.

User confirmed public test seams: pure models/services/core imports; explicit Protocol-backed plugin/UI/algorithm/job contexts; scope disposal and unavailable-native failures; subprocess native-import isolation. Real QGIS adapters and CLI static checks remain downstream.

Implemented QGIS-free models/errors, narrow service Protocols, typed plugin/UI/algorithm/job contexts, and ResourceScope ownership without a global registry. Pure tests enforce declared models <- services <- core imports and subprocess native-import isolation; fake services exercise independent contexts and cleanup/error behavior. Documented error codes, ownership, native capability opt-in and deferred adapters/CLI checks in package README. Validation: build env has no qgis; 17 Python tests pass there and under root test; root bridge test 2 pass (cached); root coverage 100% Python and bridge; Ruff lint/format pass; Python wheel/sdist build and Twine checks pass, both include new modules. All Pixi commands used PIXI_FROZEN=true PIXI_NO_INSTALL=true; earlier sandbox restore integrity failed, so environment verification is not claimed. No commit, PR, push or merge; leave In Progress until landing.

Follow-up naming rule: added repository convention in AGENTS.md and package README for QgisSdk-prefixed exception classes; renamed SDK exceptions to QgisSdkError, QgisSdkScopeClosedError and QgisSdkUnsupportedCapabilityError without unprefixed aliases. Error code values remain unchanged. New tests guard public exports and source declarations. Validation after rename: 19 Python tests pass in QGIS-free build environment and default workspace, 2 bridge tests pass (Turbo replay for test), 100% Python/bridge coverage; Ruff lint/format pass; Python wheel/sdist and Twine checks pass; isolated wheel import exposes prefixed errors. Frozen/non-installing Pixi settings used; sandbox restore integrity still unverified. No push/merge, status stays In Progress.

2026-10-16 follow-up on the confirmed lifecycle seam: added two bounded Hypothesis properties for owner/child cleanup order, idempotence and best-effort failure collection, plus two pytest-bdd scenarios for view isolation and plugin disposal. Refactored ResourceScope.close to share best-effort cleanup handling in _attempt_cleanup without changing public behavior (core-dry / solid-srp-function). Targeted QGIS-free lifecycle suite: 16 passed. Root Python: 23 passed, 17 candidate-only spike skips; Python/bridge coverage 100%. Ruff, Biome, bridge typecheck, Python wheel/sdist/Twine and bridge build passed. Full root build did not complete: Conda packaging could not reach conda-forge repodata in this sandbox. No merge; keep In Progress.
<!-- SECTION:NOTES:END -->
