---
id: TASK-118
title: Prevent layer exports from replacing their source dataset
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 118000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Safety defect found during the PyQGIS comparison: NativeLayers.export_vector(source_layer, source_path, overwrite=True) stages an export and replaces the source; a QGIS 4.2.3 temporary GeoJSON probe succeeded and changed the file inode despite Layers promising never to touch the source. This is uncommitted evidence, not a merged fix. Address file identity including aliases and provider/dataset boundaries without deleting existing user data.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Reject an export targeting the source dataset before writing, including same path, relative/absolute paths and filesystem aliases where applicable; define safe behavior when identity cannot be established.
- [ ] #2 Fake and native tests cover GeoJSON and supported GeoPackage/container cases, overwrite consent, unrelated destination success and preservation on failure; document limitations and actionable errors.
<!-- AC:END -->
