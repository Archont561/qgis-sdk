---
id: TASK-136
title: Add an interactive scaffold file tree and preview
status: To Do
assignee: []
created_date: '2026-10-28 16:43'
updated_date: '2026-10-28 17:04'
labels: []
dependencies: []
references:
  - packages/qgis-sdk-tools/src/qgis_sdk_tools/_commands/_new.py
  - packages/qgis-sdk-tools/src/qgis_sdk_tools/scaffold
priority: medium
type: enhancement
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the long flat output of qgis-sdk new (the scaffold command) with a compact terminal UI that lets plugin authors explore the generated directory tree and preview file contents before writing. Build the preview from the same resolved scaffold plan used for generation so options and output cannot drift. Preserve the hidden deprecated scaffold alias. No release milestone is assigned.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Interactive users can navigate an expandable file tree and select a file to preview its generated contents before writing; the interface has clear controls and a way to proceed or cancel.
- [ ] #2 The tree and previews match the actual generated files and contents for native and supported web and algorithm options; preview and cancellation do not write files or install dependencies.
- [ ] #3 Keep --dry-run non-mutating and retain usable deterministic plain output for non-interactive terminals and --no-input; preserve existing flags and overwrite protection and do not require interactive confirmation in scripts.
- [ ] #4 Cover tree and preview parity and keyboard navigation plus cancellation and non-TTY fallback in automated tests; document usage and avoid relying on color alone.
- [ ] #5 Coordinate the generated-file representation with the documentation project tree in TASK-138; both views must reflect the actual options and generated output rather than a manually drifting list.
<!-- AC:END -->
