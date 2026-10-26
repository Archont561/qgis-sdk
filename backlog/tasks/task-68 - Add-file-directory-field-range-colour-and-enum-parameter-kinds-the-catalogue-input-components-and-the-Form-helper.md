---
id: TASK-68
title: >-
  Add file, directory, field, range, colour and enum parameter kinds, the
  catalogue input components and the Form helper
status: In Progress
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-26 20:26'
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

2026-10-26 (slice 68a, session branch arena/c8bb6905): the kind registry (qgis_sdk.models.parameter_kinds(), ParameterKind) and the six kinds end to end - FileInput(filters=), DirectoryInput(), FieldInput(of=), Range(min, max), Colour(), Literal choices - through declarations.resolve_kind (the describer refuses a marker on the wrong stored type, a FieldInput whose of= is not a layer input, a bare FileRef input, a Literal of non-strings), the wire ('x-qgis-sdk': {kind, filters|of|step|alpha}; Range adds minimum/maximum; accepted by the Python/TS validators and documented by the generator as @qgis-sdk-kind), form_fields (kind read from the schema annotation, FieldSpec.details, coercion to FileRef/bounded numbers/hex colours), DeclaredFormDialog (QgsFieldComboBox following its layer picker, bounded spin box, QgsColorButton; file/directory refused by name until Form carries the authority), the Processing bridge (QgsProcessingParameterFile/Field/Number/Color/Enum; picker paths minted as FileRefs through a HostAuthority the provider holds and revoked after the run; HostAuthority.grant_directory, FileRef.kind directory, HOST_FINGERPRINT sha256:af91deac...), the dispatcher (FileRef rebuilt for file/directory inputs), algorithms.input_refusal shared by invoke and forms. FileRef moved to qgis_sdk.models (bridge.authority re-exports). Evidence: Python 1644+ passed / 12 skipped (QGIS-free), services harness 135 incl. the new toolbox test running all six kinds, native forms 9, Bun 235, tests/scripts 248, harnesses REFERENCE 5 / SCAFFOLD_WEB 8 / DESKTOP_ADAPTER 22 / SCAFFOLD_DESKTOP 10, ruff/biome/typecheck clean; example bridge.schema.ts regenerated. AC 1 is met for the describer/wire/Processing faces except the catalogue input components (68b). Remaining: 68b input components + ctx.files + shared authority; 68c Form, NativeForms removal, notification levels, UI001, example dialog.

2026-10-26 (slice 68b, session branch arena/00995a31): the eleven catalogue input components in qgis_sdk.ui.components (LayerPicker(kind=), FieldPicker(of=), CrsPicker, FileInput(filters=), DirectoryInput, Distance, Number(range=, step=, integer=), Text, Toggle, Choice(options=), Colour(alpha=)) - state without Qt (value()/set_value()/changed()/refresh()/snapshot(), objectName form/<name>, validation through the shared form rule qgis_sdk.ui.coerce_value), attach(ctx) binding to the UiContext (pickers list from ctx.project/ctx.layers, file inputs mint through ctx.files, listeners and widget connections dropped with the scope), mount() building the QGIS widget through qgis_sdk.adapters.qgis.components looked up by name (QgsMapLayerComboBox/QgsFieldComboBox/QgsProjectionSelectionWidget/QgsFileWidget/QgsColorButton/spin boxes/QComboBox/QCheckBox/QLineEdit) so importing qgis_sdk.ui loads no Qt; Surface.build() may return a component and SurfaceHost attaches and mounts it. ctx.files: services.Files protocol, files.FilesService over the HostAuthority with a per-owner ViewBinding, FakeFiles = the same class over a private authority; PluginContext gained files, UiContext gained files/layers/project. One HostAuthority per runtime in native_plugin_context shared by NativeProcessing(authority=), ctx.files and HostServices.from_context (defaults to context.files.authority). Form coercion refuses negative metres. Contract tests in tests/ui_component_contract.py run by test_ui_components.py (fake) and test_ui_components_native.py (mounted). Evidence: Python quick 1741 passed / 12 skipped, native services 135, DESKTOP_ADAPTER 22, SCAFFOLD_DESKTOP 10, REFERENCE 5, HEADLESS_LIFECYCLE 5, COEXISTENCE 23, NATIVE_SERVICES_SMOKE 7; bridge generate --check and the example schema unchanged (no host schema change, fingerprint unchanged); ruff clean. AC 2 met for the components; AC 1 remains open on the Form half (68c). Remaining: 68c Form.for_action/from_schema/fields, NativeForms/DeclaredFormDialog removal, notification levels, with_action, UI001, example dialog.
<!-- SECTION:NOTES:END -->
