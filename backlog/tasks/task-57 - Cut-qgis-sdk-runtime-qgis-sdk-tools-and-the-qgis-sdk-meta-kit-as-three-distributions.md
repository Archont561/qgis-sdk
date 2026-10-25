---
id: TASK-57
title: >-
  Cut qgis-sdk-runtime, qgis-sdk-tools and the qgis-sdk meta kit as three
  distributions
status: In Progress
assignee: []
created_date: '2026-10-25T14:50:00Z'
updated_date: '2026-10-25 18:04'
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
Step 2 of decision-35, un-gated from the contract freeze by decision-36 and executed in the 0.5.0 line. Three pyproject.toml files: qgis-sdk-runtime (packages/qgis-sdk-runtime, import qgis_sdk, stdlib-only), qgis-sdk-tools (packages/qgis-sdk-tools, import qgis_sdk_tools, the qgis-sdk console script, a tested runtime range), and qgis-sdk (packages/qgis-sdk-python) as a code-free kit pinning both with extras for options. Delivered on PR #78 in two commit series: first the distributions under the existing python scope (stamp/verify/build handle the three manifests at one version, three-output recipe, path updates); then the independent runtime-v* and tools-v* scopes, one publish step per distribution, the qgis-sdk check version diagnostic and the migration note. The prerelease-tag rehearsal of the pipeline follows the merge and needs an explicit request. The PyPI projects exist at placeholder 0.0.0 with trusted publishing bound to release.yml / environment pypi; the placeholders are yanked after the first real publish.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pip install qgis-sdk installs the runtime and tools at same-release pins; pip install qgis-sdk-runtime installs only qgis_sdk with no Typer; no two wheels write the same top-level directory.
- [x] #2 release.py plan/stamp/verify handle runtime-v*, tools-v* and python-v* independently and refuse a tools release whose runtime range does not include the runtime at HEAD.
- [ ] #3 release.yml publishes each distribution from its own pypa/gh-action-pypi-publish step and the recipe builds three outputs; a dry run against TestPyPI or a workflow_dispatch rehearsal is recorded in doc-14.
- [x] #4 qgis-sdk check reports a pinned runtime or generated client outside the versions this tools release supports, and the migration note states what console users and plugin authors install.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
PR #78 (branch arena/27015bd3-qgis-sdk) carries the whole task. AC1: three wheels built and twine-checked, disjoint top-level dirs, runtime alone imports with no Typer, kit installs all three at one version in a clean venv (pip check clean). AC2: release.py scopes python (kit train), runtime, tools; stamp per scope; verify-versions refuses a tools range that excludes HEAD's runtime and a kit pin that leads the manifest it names; sort_tags/commits_for_scope/scope_ships per distribution; 190 tests in tests/scripts/test_release.py. AC3: release.yml publishes each wheel from its own pypa step (dist/pypi/<runtime|tools|kit>) and each Conda output from its own upload, recipe has three outputs with per-distribution context versions; the prerelease-tag rehearsal is NOT run yet (no dispatch from the sandbox) - recorded as pending in doc-14 'Split release pipeline rehearsal'. AC4: qgis-sdk check rules VERSION001 (runtime/kit pin outside the tools' tested range) and VERSION002 (generated client from another contract version), tests/test_check_versions.py (26); migration note in doc-12 '0.5.0 migration notes' states who installs what.
<!-- SECTION:NOTES:END -->
