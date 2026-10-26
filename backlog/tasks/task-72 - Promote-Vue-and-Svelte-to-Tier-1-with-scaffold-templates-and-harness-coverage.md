---
id: TASK-72
title: Promote Vue and Svelte to Tier 1 with scaffold templates and harness coverage
status: To Do
assignee: []
created_date: '2026-10-26T09:06:00Z'
labels: []
dependencies:
  - TASK-69
  - TASK-70
priority: low
type: enhancement
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-47 point 4. Unscheduled: created so the promotion path exists, picked up when a user asks for either template. qgis-sdk new --ui vue and --ui svelte templates with exact npm pins owned by the release pipeline (decision-18/41), each run through the scaffold-web harness and test-reference-web, using the ./vue or ./svelte adapter and the qgis-sdk-ui wrappers; doc-13's tier table and the package README updated. Either framework may be promoted alone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The new template scaffolds, checks, builds and runs its page inside a real QWebEngineView through the scaffold-web harness, with the pins moved by release.py stamp --scope typescript.
- [ ] #2 The tier table in doc-13 and the bridge and qgis-sdk-ui READMEs name the framework as Tier 1; the scaffold questionnaire offers it.
<!-- AC:END -->
