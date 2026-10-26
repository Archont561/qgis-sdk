---
id: TASK-68
title: >-
  Add file, directory, field, range, colour and enum parameter kinds and the
  standard native surfaces
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-26T10:01:00Z'
labels: []
milestone: m-6
dependencies:
  - TASK-67
  - TASK-63
type: enhancement
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-46 points 1 and 2. Each new kind is complete across hosts: marker in qgis_sdk.models.parameters (FileInput(filters=), DirectoryInput() returning FileRef, FieldInput(of=), Range(min, max), Colour(), Enum/Literal choices), widget family in qgis_sdk.ui, Qt widget in the native form, Processing parameter in the provider adapter, JSON-schema annotation on the wire. Standard surfaces DeclaredForm (initial=, accept hook), JobProgressDock and LogPanel ship in the runtime and are named by actions through dialog=/dock=; ctx.ui.form(action_id, initial=) opens a declared form from a handler; ctx.notifications gains warning, critical, success and with_action(label, action_id).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every new kind describes, renders in the native form, maps to a Processing parameter and round-trips through the page's schema; a kind missing any of the four is refused by the describer (pure tests + qgis native tests); FileInput/DirectoryInput return FileRef and never a path.
- [ ] #2 DeclaredForm, JobProgressDock and LogPanel open through dialog=/dock= under a QgsApplication, dispose with the view scope, and JobProgressDock cancels the job; ctx.ui.form returns values or None; the notification levels reach the message bar (native tests, desktop harness).
- [ ] #3 doc-12 documents the kinds table and the standard surfaces; the example plugin uses at least one new kind; the Python suite and services harness are green.
- [ ] #4 Every widget a generated surface creates carries an objectName derived from the declared id (form/<field>, buttons/<name>) and check reports UI001 for a generated surface widget without one, so decision-51 snapshots have stable ids from the first release (pure + native tests).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: AC 4 added for decision-51 (stable objectNames).
<!-- SECTION:NOTES:END -->
