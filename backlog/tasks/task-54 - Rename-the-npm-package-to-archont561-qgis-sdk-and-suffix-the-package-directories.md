---
id: TASK-54
title: >-
  Rename the npm package to @archont561/qgis-sdk and suffix the package
  directories
status: Done
assignee: []
created_date: '2026-10-25 10:17'
updated_date: '2026-10-25 10:42'
labels:
  - release
  - tooling
milestone: m-3
dependencies: []
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner request 2026-10-25: 'bridge' is limiting because web-view UI will ship from the same package. Rename @archont561/qgis-sdk-bridge to @archont561/qgis-sdk (decision-33), move packages/qgis-sdk to packages/qgis-sdk-python and packages/qgis-sdk-bridge to packages/qgis-sdk-typescript, and update every reference: CI/release/autorelease workflows, Pixi and Bun tooling, Codecov flags, scripts/release.py scope aliases, generators and tests, READMEs, skills, and the backlog. Historical release evidence in closed tasks keeps the names it recorded.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both package directories carry the language suffix and every workspace reference (workflows, pixi.toml, package.json scripts, bunfig/codecov, generators, tests, AGENTS.md and skills) resolves to the new paths
- [x] #2 packages/qgis-sdk-typescript/package.json declares @archont561/qgis-sdk with the same exports as 0.2.0; scripts/release.py maps @archont561/qgis-sdk, qgis-sdk-typescript and qgis-sdk-python to their scopes and keeps qgis-sdk-bridge as a legacy alias
- [x] #3 decision-33 records the rename, doc-13 is retitled with a migration note, milestones and READMEs use the current name, and the full verify gate (lint, format, test-release-tool, lint-github-actions, typecheck, biome, bun test, coverage, generated-client check, Python suite, tests/scripts) passes
- [x] #4 Operator follow-ups are documented: provision the npm trusted publisher for @archont561/qgis-sdk before ts-v0.3.0 and deprecate @archont561/qgis-sdk-bridge after the first publish
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered in PR #66 (commits 1843715, 83412c1, fa2ac33) on arena/e4d16e74-qgis-sdk. Directories packages/qgis-sdk-python and packages/qgis-sdk-typescript; npm name @archont561/qgis-sdk (manifest still 0.2.0, first publish under the new name will be 0.3.0). Every workspace reference updated; closed tasks keep the names of published artifacts as recorded (decision-33 rule 6). Gate before merge: lint-python, format-python-check, test-release-tool (191), lint-github-actions (with shellcheck), typecheck, biome-check, bun test (197), coverage TS 96.49% / Py 97.03%, generate_bridge_clients.py --check, Python suite 1118 passed / 35 skipped, release.py verify-versions. CI checks on PR #66 green on ubuntu, macOS and Windows. Operator follow-ups moved to TASK-55 AC #4 and the PR body.
<!-- SECTION:NOTES:END -->
