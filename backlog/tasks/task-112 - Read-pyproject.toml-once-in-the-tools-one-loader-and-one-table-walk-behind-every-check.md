---
id: TASK-112
title: >-
  Read pyproject.toml once in the tools: one loader and one table walk behind
  every check
status: To Do
assignee: []
created_date: '2026-10-27 21:55'
labels: []
milestone: m-7
dependencies: []
priority: low
type: chore
ordinal: 112000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-10-27 (clean-code core-dry-extraction, core-dry-single-source). The tools parse the plugin's pyproject.toml in eight places, each with its own tomllib.loads(...read_text(encoding='utf-8')) call and its own TOMLDecodeError policy: bundle/validate.py:58, check/project.py:212, check/versions.py:95/266/368/458, devtools/installs.py:233, project.py:169. project.py:247 already owns _table(data, *keys) for walking [tool.qgis-sdk.*], yet bundle/validate.py:61-66 and check/project.py:217-222 re-implement that walk inline over their own _CONFIG_TABLE tuples. The same package (bundle/vendor.py:30) keeps a dead _IMPORT_PREFIX regex that nothing reads since _rewrite_import_line took over the import form. Smallest fix: one read_pyproject(root) in qgis_sdk_tools.project that returns the parsed mapping or the parse failure once, and a public table(data, *keys); every site above calls them. Behaviour-preserving: the diagnostics (CONFIG001 text, which file is read, what happens on a missing file) stay byte-identical and the existing tests pass unchanged. Non-goals: no new check rule, no change to the [tool.qgis-sdk] schema, no caching across commands.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 qgis_sdk_tools.project exposes one pyproject loader and one table walk; grep for tomllib.loads in src/qgis_sdk_tools returns a single site and the inline _CONFIG_TABLE loops in bundle/validate.py and check/project.py are gone.
- [ ] #2 Every existing test under packages/qgis-sdk-python/tests and tests/scripts passes without edits to its expectations (the diagnostics and return values of each caller are unchanged).
- [ ] #3 The unused _IMPORT_PREFIX constant in bundle/vendor.py is removed and the rewrite tests still cover both the from-form and the import-form.
<!-- AC:END -->
