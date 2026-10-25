---
id: TASK-57
title: >-
  Cut qgis-sdk-runtime, qgis-sdk-tools and the qgis-sdk meta kit as three
  distributions
status: To Do
assignee: []
created_date: '2026-10-25T14:50:00Z'
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
Step 2 of decision-35, gated on the contract freeze (an explicit decision that PluginContext, the service protocols, the description schema and the bridge protocol stop moving between minors). Three pyproject.toml files: qgis-sdk-runtime (import qgis_sdk, stdlib-only, runtime major bumps iff a contract version bumps), qgis-sdk-tools (import qgis_sdk_tools, the qgis-sdk console script, a tested runtime range), and qgis-sdk as a code-free meta distribution depending on both with extras for options. release.py gains runtime-v* and tools-v* scopes; release.yml publishes each distribution from its own step; the conda recipe produces the three outputs for the qgis-sdk* channel binding. The PyPI projects already exist at placeholder 0.0.0 with trusted publishing bound to release.yml / environment pypi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pip install qgis-sdk installs the runtime and tools at same-release pins; pip install qgis-sdk-runtime installs only qgis_sdk with no Typer; no two wheels write the same top-level directory.
- [ ] #2 release.py plan/stamp/verify handle runtime-v*, tools-v* and python-v* independently and refuse a tools release whose runtime range does not include the runtime at HEAD.
- [ ] #3 release.yml publishes each distribution from its own pypa/gh-action-pypi-publish step and the recipe builds three outputs; a dry run against TestPyPI or a workflow_dispatch rehearsal is recorded in doc-14.
- [ ] #4 qgis-sdk check reports a pinned runtime or generated client outside the versions this tools release supports, and the migration note states what console users and plugin authors install.
<!-- AC:END -->
