---
id: TASK-57
title: >-
  Cut qgis-sdk-runtime, qgis-sdk-tools and the qgis-sdk meta kit as three
  distributions
status: In Progress
assignee: []
created_date: '2026-10-25T14:50:00Z'
updated_date: '2026-10-25 17:41'
labels: []
milestone: m-4
dependencies:
  - TASK-56
  - TASK-8
  - TASK-30
priority: medium
type: enhancement
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Step 2 of decision-35, un-gated from the contract freeze by decision-36 and executed in the 0.5.0 line. Three pyproject.toml files: qgis-sdk-runtime (packages/qgis-sdk-runtime, import qgis_sdk, stdlib-only), qgis-sdk-tools (packages/qgis-sdk-tools, import qgis_sdk_tools, the qgis-sdk console script, a tested runtime range), and qgis-sdk (packages/qgis-sdk-python) as a code-free kit pinning both with extras for options. Delivered in two PRs: first the distributions under the existing python scope (stamp/verify/build handle the three manifests at one version, three-output recipe, path updates); then the independent runtime-v* and tools-v* scopes, one publish step per distribution, the TestPyPI/workflow_dispatch rehearsal, the qgis-sdk check version diagnostic and the migration note. The PyPI projects exist at placeholder 0.0.0 with trusted publishing bound to release.yml / environment pypi; the placeholders are yanked after the first real publish.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pip install qgis-sdk installs the runtime and tools at same-release pins; pip install qgis-sdk-runtime installs only qgis_sdk with no Typer; no two wheels write the same top-level directory.
- [ ] #2 release.py plan/stamp/verify handle runtime-v*, tools-v* and python-v* independently and refuse a tools release whose runtime range does not include the runtime at HEAD.
- [ ] #3 release.yml publishes each distribution from its own pypa/gh-action-pypi-publish step and the recipe builds three outputs; a dry run against TestPyPI or a workflow_dispatch rehearsal is recorded in doc-14.
- [ ] #4 qgis-sdk check reports a pinned runtime or generated client outside the versions this tools release supports, and the migration note states what console users and plugin authors install.
<!-- AC:END -->
