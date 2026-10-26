---
id: TASK-68
title: >-
  Add file, directory, field, range, colour and enum parameter kinds, the
  catalogue input components and the Form helper
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-26T11:01:00Z'
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
decision-46 point 1 and decision-55 points 3, 4 and 7 (UI001). Each new kind is complete across hosts: marker in qgis_sdk.models.parameters (FileInput(filters=), DirectoryInput() returning FileRef, FieldInput(of=), Range(min, max), Colour(), Enum/Literal choices), widget family in qgis_sdk.ui, catalogue input component, Processing parameter in the provider adapter, JSON-schema annotation on the wire. The input components of the catalogue - LayerPicker(kind=), FieldPicker(of=), CrsPicker, FileInput, DirectoryInput, Distance, Number(range=), Text, Toggle, Choice(options=), Colour - each wrapping the QGIS widget where one exists, speaking models, refreshing through streams, with a fake rendering and a stable objectName. Form.for_action(ctx, action_id, initial=), Form.from_schema(schema) and Form(fields=[...]) over the kept form_fields rule, with values()/changed/submit(); NativeForms and DeclaredFormDialog removed in favour of Form with the migration in doc-12's 0.7.0 notes; notification levels and with_action; Qt imported lazily inside the catalogue, never at module top.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every new kind describes, renders through its catalogue input, maps to a Processing parameter and round-trips through the page's schema; a kind missing any of the four is refused by the describer (pure tests + qgis native tests); FileInput/DirectoryInput return FileRef and never a path.
- [ ] #2 Each input component builds natively under a QgsApplication and under the fake with the same contract tests, returns a model from value(), refreshes on its stream (LayerPicker on project changes) and unsubscribes with the scope; importing qgis_sdk.ui without Qt installed succeeds (pure tests).
- [ ] #3 Form.for_action renders an action's inputs with initial values, Form.from_schema and Form(fields=) build the same tree, submit() dispatches through UiContext.actions, and NativeForms/DeclaredFormDialog are gone with doc-12 naming the replacement (native + pure tests; desktop harness updated).
- [ ] #4 Every widget a catalogue component creates carries an objectName derived from its name (form/<field>, buttons/<name>) and check reports UI001 for an interactive widget without one, so decision-51 snapshots have stable ids from the first release (pure + native tests).
- [ ] #5 doc-12 documents the kinds table, the input components and Form; the example plugin builds its buffer dialog from Form.for_action plus one hand-placed component; the Python suite and services harness are green.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: AC 4 added for decision-51 (stable objectNames).
2026-10-26: rewritten for decision-55 - input components and Form helper instead of standard surfaces; NativeForms migration; containers, feedback, wiring moved to TASK-96.
<!-- SECTION:NOTES:END -->
