---
id: TASK-8
title: Build a validated QGIS-installable plugin ZIP
status: In Progress
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-25 16:18'
labels: []
milestone: m-3
dependencies:
  - TASK-1
  - TASK-16
  - TASK-19
  - TASK-24
  - TASK-12
priority: high
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement qgis-sdk build with the accepted plugin-private pure-Python-first runtime policy. Validate dependencies/licenses, safe deterministic contents and two-plugin import isolation; do not install/test/publish implicitly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ZIP root has the plugin directory/layout and metadata expected by QGIS.
- [ ] #2 Archive includes required Python runtime modules and production assets while excluding tests, caches, dev tooling, and frontend dev server assets.
- [ ] #3 Build validates metadata, entry point, declared assets, and reports missing or unsupported runtime dependencies.
- [ ] #4 A clean supported QGIS profile can install and load a sample archive.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
decision-35 (2026-10-25): the ZIP ships the runtime tree (src/qgis_sdk, minus qgis_sdk.testing) under an import-renamed plugin-private path and never the tools tree (src/qgis_sdk_tools). After TASK-56 that exclusion is a package boundary, not a list.

Landed in session arena/7a0272e6 (sprint 3, doc-16). qgis-sdk build [PATH] [--out DIR] [--no-web] [--json] over qgis_sdk_tools.bundle.build_plugin (module named bundle because build/ is gitignored). check_project first (same diagnostics), then ENTRY001 (classFactory in __init__.py), DEP001 (top-level import neither stdlib, QGIS/Qt, runtime nor plugin; also any qgis_sdk_tools import; [tool.qgis-sdk.build] external declares what the target QGIS ships), DEP002 (qgis_sdk.testing), WEB001 (web project without built page); errors refuse with exit 1 and nothing written. Web: runs the project's own build script through its lockfile manager, never installs (exit 2 with the install command); --no-web ships <plugin>/web as is. Staging excludes __pycache__, *.pyc, tests, .qgis-sdk, .pytest_cache, node_modules; runtime vendored to <plugin>/_vendor/qgis_sdk minus testing with AST-located import rewrite (keeps line numbers) in the copy and the plugin, NOTICE with runtime version + MIT; deterministic ZIP (sorted, SOURCE_DATE_EPOCH or 1980, modes normalised), single root <plugin>/, dist/<plugin>-<version>.zip. Tests: tests/test_bundle.py (25, incl. importing the extracted archive in-process), tests/test_bundle_cli.py (7). Evidence AC4/decision-3: QGIS_SDK_BUILD_INSTALL=1 tests/test_bundle_native.py unpacks two built plugins into a clean profile's python/plugins, starts QGIS Desktop with a meta_path finder refusing qgis_sdk: both load, ping, run distinct vendored runtimes, qgis_sdk never imported (1 passed, QGIS 4.2.3). Licence validation beyond the SDK's own NOTICE is not implemented: the ZIP carries no third-party code (DEP001 refuses it).
<!-- SECTION:NOTES:END -->
