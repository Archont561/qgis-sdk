---
id: TASK-132
title: Design QGIS-aware diagnostics and a discoverable check rule catalog
status: To Do
assignee: []
created_date: '2026-10-28 16:24'
labels: []
dependencies: []
references:
  - 'https://github.com/osgeosuomi/flake8-qgis'
  - 'https://github.com/geociencio/qgis-plugin-analyzer'
priority: medium
type: enhancement
ordinal: 132000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluate ideas from flake8-qgis and qgis-plugin-analyzer for SDK-owned, source-only developer diagnostics beyond the worker-specific TASK-117. Existing checks already have stable IDs, locations, JSON and remediation; do not replace them or add third-party dependencies by default.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Select and document a small high-confidence set of QGIS 4/Qt 6 migration, protected import, ignored success-result, Processing and asset checks based on representative SDK projects; distinguish uncertain heuristics as warnings and document false positives and limits.
- [ ] #2 Provide a discoverable rule catalog with IDs, severity, explanation, examples and remediation; evaluate scoped checks and explicit configuration or suppression without breaking current IDs, ordering, JSON output or check/build behavior.
- [ ] #3 Tests cover passing and failing snippets, aliases and edge cases, source-only behavior and deterministic reports; coordinate security rules with TASK-105 and worker analysis with TASK-117 rather than duplicating or claiming static analysis proves safety.
<!-- AC:END -->
