---
id: TASK-111
title: >-
  Split the eight longest hand-written source files into packages behind
  unchanged barrels
status: In Progress
assignee: []
created_date: '2026-10-27 21:11'
updated_date: '2026-10-27 21:31'
labels: []
milestone: m-7
dependencies: []
priority: low
type: chore
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Housekeeping chosen on 2026-10-27 after a file-length pass over packages/*/src: eight hand-written files of 740-1575 lines are split into directories of private sub-modules (underscore names) whose __init__.py or entry file re-exports exactly the names importable today. The generated processing modules (native.py, gdal.py, qgis.py, pdal.py) and scripts/release.py are out of scope; dispatch.py, testing.ts and scaffold/web.py stay whole. No behaviour changes, no public module path changes, no generated artifact changes. One commit per file so each split is independently revertible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 qgis_sdk/jobs.py, qgis_sdk/declarations.py, qgis_sdk/bridge/host.py and qgis_sdk/ui/components.py are packages whose __init__.py keeps every name the modules exported, with an explicit __all__; test_pure_imports.py layer paths point at the packages.
- [x] #2 qgis_sdk_tools/generate.py is a package and qgis_sdk_tools/__main__.py a thin entry over private command modules; CONTRACT_FINGERPRINT and the generated TypeScript are byte-identical.
- [x] #3 qgis-sdk-typescript src/stores.ts and src/bridge.ts are entry barrels over sub-directories; the published ./bridge entry and every exported type are unchanged and isolatedDeclarations still passes.
- [x] #4 Every existing import site in src, tests and examples builds and runs unchanged; HOST_FINGERPRINT is unchanged; git diff shows nothing under generated/ or packages/qgis-sdk-runtime/src/qgis_sdk/processing; the full Python and Bun suites and lint, format and typecheck gates are green.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-27: eight commits on the PR branch, one per file, in order: jobs, declarations, bridge.host, ui.components (runtime), generate and __main__ (tools), stores.ts and bridge.ts (bridge). Verified per commit: ruff check/format, the narrow test files, then the full Python suite (1964 passed, 48 skipped) or the Bun suite (310 pass). Final gate: lint-python, format-python-check, typecheck, biome-check (186 files), root build and test (config 6, docs 34, bridge 310, alias 12, ui 100, ui alias 13), tests/scripts 262, docs-build, generate_bridge_clients.py --check (every generated file up to date), HOST_FINGERPRINT sha256:16790dc8 unchanged, git diff against main shows nothing under generated/ or qgis_sdk/processing; test-reference-example 7, scaffold-web harness 8 and the build-install harness 1 passed. Two incidental re-points: scripts/release.py reads PLUGIN_DESCRIPTION_SCHEMA_VERSION from declarations/_contract.py; test_quiesce imports JobContext from qgis_sdk.core. Status stays In Progress until the pull request is merged.
<!-- SECTION:NOTES:END -->
