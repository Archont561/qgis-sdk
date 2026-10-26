---
id: TASK-62
title: >-
  Scaffold the page on the pinned bridge release for users and on the workspace
  bridge inside the repository
status: Done
assignee: []
created_date: '2026-10-26 07:49'
updated_date: '2026-10-26 11:59'
labels: []
milestone: m-5
dependencies:
  - TASK-61
type: enhancement
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
qgis-sdk new --web writes web/package.json with @archont561/qgis-sdk at the exact release this qgis-sdk-tools was qualified with (SDK_NPM_VERSION); release.py stamp --scope typescript now moves that pin with every bridge release and verify-versions reads it. Inside this repository the same scaffold must run on the checkout's packages/qgis-sdk-typescript instead: an explicit --sdk-dependency SPEC flag (refused without --web, no path auto-detection), examples/*/web join the Bun workspace with workspace:* (root lockfile, turbo builds the bridge before the example's Vitest, CI task test-reference-web), and the opt-in web harnesses receive a bun pm pack tarball of the workspace bridge through the same flag. Recorded in decision-41.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scaffold/web.py SDK_NPM_VERSION is rewritten by release.py stamp --scope typescript and reported by verify-versions as the scaffold pin; a tests/scripts test fails when the pin disagrees with packages/qgis-sdk-typescript/package.json.
- [x] #2 qgis-sdk new --sdk-dependency SPEC (and ScaffoldOptions.resolve(sdk_dependency=)) replaces only the @archont561/qgis-sdk value of web/package.json; blank or whitespace specs and a spec without --web are refused; covered by pure tests.
- [x] #3 examples/simple/web is a Bun workspace member depending on workspace:*, its own bun.lock is gone, bun install --frozen-lockfile passes at the root, and a pure test proves its package.json equals the scaffold's for that spec; pixi run -e bun test-reference-web runs its Vitest suite in CI after building the bridge.
- [x] #4 QGIS_SDK_REFERENCE=1 and QGIS_SDK_SCAFFOLD_WEB=1 harnesses scaffold with --sdk-dependency file:<tarball of the workspace bridge> and pass; doc-12, doc-14, the example README, decision-41, m-5 and doc-4 describe the mechanism.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Shipped in PR #90 (merged as 56e074e) and validated on main: release.py stamp --scope typescript moves SDK_NPM_VERSION and verify-versions reports it; qgis-sdk new --sdk-dependency SPEC is refused without --web or blank; examples/simple/web is a Bun workspace member (workspace:*, root lockfile, test-reference-web in CI); QGIS_SDK_REFERENCE=1 and QGIS_SDK_SCAFFOLD_WEB=1 scaffold on a bun pm pack tarball of the workspace bridge. Closed in the TASK-63 PR (m-5 sprint 1) after re-running tests/scripts (241 passed), test-reference-web (4 passed) and the QGIS_SDK_REFERENCE=1 harness (5 passed) on top of the provider redesign.
<!-- SECTION:NOTES:END -->
