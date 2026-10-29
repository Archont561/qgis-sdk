---
id: TASK-118
title: Prevent layer exports from replacing their source dataset
status: Done
assignee: []
created_date: '2026-10-28 15:58'
updated_date: '2026-10-29 09:11'
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
- [x] #1 Reject an export targeting the source dataset before writing, including same path, relative/absolute paths and filesystem aliases where applicable; define safe behavior when identity cannot be established.
- [x] #2 Fake and native tests cover GeoJSON and supported GeoPackage/container cases, overwrite consent, unrelated destination success and preservation on failure; document limitations and actionable errors.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add shared fake/native contract regression tests at Layers.export_vector, then implement a fail-closed source-dataset identity check before writing. Cover same-path and aliases plus GeoPackage containers and unverifiable provider sources; validate pure and native contracts and document limitations.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented and merged in PR #126 at d816192bbc9fee16aaa41274b38384ceca525603; PR CI and documentation checks passed. Capture file identity at open, decode OGR container URIs, fail closed for unverified or indirect sources, and recheck before staged commit. Qualified native source drivers are GeoJSON, GPKG and ESRI Shapefile. Without overwrite, atomic publication uses a hard link and fails closed when unsupported. Filesystem paths must remain stable between the final check and commit. Fake/native contract, VRT and shapefile regressions passed; native-enabled services and export policy tests 193 passed. Full workspace coverage 6/6 tasks, Python 1913 passed, 50 skipped, 96.96%; Ruff and docs link check passed. Native QGIS evidence remains Linux-only.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Prevented source dataset replacement and added fake/native regressions; merged and qualified by PR #126.
<!-- SECTION:FINAL_SUMMARY:END -->
