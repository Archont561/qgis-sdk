---
id: TASK-118
title: Prevent layer exports from replacing their source dataset
status: In Progress
assignee: []
created_date: '2026-10-28 15:58'
updated_date: '2026-10-28 18:26'
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
Implemented on the session branch; not yet merged. Capture file identity at open, decode OGR container URIs, fail closed for unverified or indirect sources, and recheck before staged commit. Qualified native source drivers are GeoJSON, GPKG and ESRI Shapefile. Without overwrite, atomic publication uses a hard link and fails closed when unsupported. Filesystem paths must remain stable between the final check and commit. Fake/native contract, VRT and shapefile regressions passed; native service suite 174 passed. Full workspace coverage: Python 1907 passed, 50 skipped, 96.97%; all six workspace coverage tasks passed. Ruff, docs link check and backlog doctor passed.

PR-readiness review found unresolved source-identity defects: a native QGIS probe opened a symlink to A, retargeted it to B before export, and export_vector(..., B, overwrite=True) replaced B; capture_source retained only the old resolved target, while QGIS read B. Similarly, opening a relative source in directory A, then changing cwd to directory B before export caused QGIS to read and replace B/source.geojson. Paths stayed stable during each export. A fake probe also opened a declared missing source, then created it and a hard-link alias; export to the alias succeeded because virtual identity bypassed inode checks. Add fake/native regressions and address these before considering acceptance complete. Review used temporary files only.

Follow-up fixed the review findings: retain and re-resolve the original provider path before writing and before commit, refusing retargeted links and relative paths that now resolve elsewhere. A fake declared virtual source that materializes is refused until reopened. Fake/native contract regressions cover retargeting before and during writing, changed working directories, successful stable symlinks and source preservation; fake-specific coverage checks virtual materialization. Native-enabled services plus export policy: 193 passed. Workspace coverage: Python 1913 passed, 50 skipped, 96.96%, six tasks successful. Whole-tree Ruff and docs link check passed. Windows/macOS execution remains unverified locally; cross-process mutation after the final check is still outside the guarantee.
<!-- SECTION:NOTES:END -->
