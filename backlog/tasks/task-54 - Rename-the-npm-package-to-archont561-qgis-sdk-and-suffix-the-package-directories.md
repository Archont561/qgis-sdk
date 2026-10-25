---
id: TASK-54
title: >-
  Rename the npm package to @archont561/qgis-sdk and suffix the package
  directories
status: In Progress
assignee: []
created_date: '2026-10-25 10:17'
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
- [ ] #1 Both package directories carry the language suffix and every workspace reference (workflows, pixi.toml, package.json scripts, bunfig/codecov, generators, tests, AGENTS.md and skills) resolves to the new paths
- [ ] #2 packages/qgis-sdk-typescript/package.json declares @archont561/qgis-sdk with the same exports as 0.2.0; scripts/release.py maps @archont561/qgis-sdk, qgis-sdk-typescript and qgis-sdk-python to their scopes and keeps qgis-sdk-bridge as a legacy alias
- [ ] #3 decision-33 records the rename, doc-13 is retitled with a migration note, milestones and READMEs use the current name, and the full verify gate (lint, format, test-release-tool, lint-github-actions, typecheck, biome, bun test, coverage, generated-client check, Python suite, tests/scripts) passes
- [ ] #4 Operator follow-ups are documented: provision the npm trusted publisher for @archont561/qgis-sdk before ts-v0.3.0 and deprecate @archont561/qgis-sdk-bridge after the first publish
<!-- AC:END -->
