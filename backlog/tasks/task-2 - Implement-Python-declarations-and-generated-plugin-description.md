---
id: TASK-2
title: Implement Python declarations and generated plugin description
status: In Progress
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-17 16:26'
labels: []
milestone: m-0
dependencies:
  - TASK-11
  - TASK-12
priority: high
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement the Python-first declarative authoring foundation and deterministic description generation described in ADR-1 and ADR-2. Python handlers contain behavior; JSON, if emitted, is derived/interchange only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decorators/typed declarations can be inspected and validated without starting QGIS.
- [x] #2 Generated description is deterministic, versioned, and contains serializable structure rather than callables or live QGIS objects.
- [x] #3 Invalid declarations produce actionable diagnostics and have pure-Python tests.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement approved public seams: plugin/action metadata decorators, describe_plugin, typed versioned deterministic description and prefixed diagnostics. Use pure-Python red/green slices; document supported signatures/types and deferred runtime scope; run root checks and coverage.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented user-approved experimental public contract: metadata-only plugin/action decorators, describe_plugin, typed descriptions, schema_version 1 and deterministic JSON. 34 public declaration tests plus isolated native-free inspection cover schemas, diagnostics, inheritance and nonexecution. Final validation from an unverified restore: root test 226 passed/1 optional smoke skipped; root coverage 201 passed/1 skipped, Python 100%, TypeScript 100% (90 bridge tests). Ruff lint/scoped format, Biome and bridge typecheck pass. Root build remains blocked by existing Conda conda-forge repodata TLS handshake EOF; no dependency or lockfile changes. Task stays In Progress pending review/merge.
<!-- SECTION:NOTES:END -->
