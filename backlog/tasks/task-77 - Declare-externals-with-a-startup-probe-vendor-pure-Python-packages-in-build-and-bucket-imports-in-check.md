---
id: TASK-77
title: >-
  Declare externals with a startup probe, vendor pure-Python packages in build,
  and bucket imports in check
status: Done
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-29 22:10'
labels: []
milestone: m-7
dependencies:
  - TASK-64
type: enhancement
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-50. [tool.qgis-sdk.build] external accepts tables {import, requirement, reason}; the generated classFactory probes externals before constructing the plugin and shows one message-bar error with the host-specific install hint on failure, leaving the plugin cleanly unloaded; externals are rendered into the generated metadata.txt description. [tool.qgis-sdk.build] vendor = [...] copies installed pure-Python distributions under <plugin>/_vendor/ with the import rewrite, records name/version in the notice and licenses under _vendor/LICENSES/; compiled extensions are refused with DEP003, missing transitive dependencies with DEP004. check buckets every import (stdlib, host, runtime, plugin, vendored, external, unknown) and reports unknown ones as DEP001 at check time. The SDK still installs nothing on the user's machine.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A missing external yields the message-bar error naming the package and the hint for the detected host, and the plugin is not half-initialised (qgis native test); the externals appear in the generated metadata.txt (pure test).
- [x] #2 build vendors a pure-Python distribution with its license and rewritten imports and the plugin imports it from the ZIP; a compiled distribution is refused with DEP003 and a missing transitive dependency with DEP004 (pure tests on fixture distributions; build-install harness for one vendored package).
- [x] #3 check prints each import's bucket and reports DEP001 with both exits before any build; doc-12 states that pandas-class packages are externals with a probe, never vendored.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Re-scoped 2026-10-27 from m-6 (0.7.0) to m-7 (0.8.0): externals and pure-Python vendoring are a build feature with no UI-toolkit dependency; it blocks nothing in m-6 and nothing in m-6 blocks it, and 0.7.0 ships what is already qualified. Lands in m-7 as its own small pull request before the gate.

Session follow-up: the owner requested an opt-in, end-user-approved dependency installation option. TASK-123 is a policy spike only; decision-50 remains in force and TASK-77 must not install packages unless a later decision explicitly revises that policy.
2026-10-29 implemented as its own PR before the 0.8.0 gate. Externals: `[tool.qgis-sdk.build] external` accepts bare roots and `{import, requirement, reason}` tables (`ProjectConfig.build`, `BuildConfig`, `ExternalPackage`), renders into `metadata.txt` as `Requires: ...`, and the generated `classFactory` imports each one *before* `host(...)` runs, so a missing package never leaves a half-built plugin; it shows one message-bar error naming the package, the reason and the host's install command (OSGeo4W Shell, QGIS.app's pip3, `python3 -m pip install --user`) and returns `None` so QGIS leaves it unloaded. `dev` gets the same probe because it shares the generator. Vendoring: `vendor = [...]` copies installed pure-Python distributions under `<plugin>/_vendor/`, rewrites imports of the vendored roots in the plugin and inside the copies (`rewrite_imports(roots=...)`, generalised from the runtime-only rewrite), puts licences in `_vendor/LICENSES/<name>-<version>-<file>`, and records name/version in `_vendor/NOTICE`; `BuildResult.vendored` names them. New `qgis_sdk_tools.distributions` reads a distribution's roots, compiled files, requirements and licences from metadata without importing it. Buckets: `qgis_sdk_tools.check.buckets` sorts every import root (stdlib, host, runtime, plugin, vendored, external, unknown), `CheckReport.imports` carries the listing, `check --imports` prints it and `--json` includes it; unknown roots are `DEP001` at check time with both exits in the remediation, and the build now inherits those findings instead of duplicating them (validate.py keeps only `WEB001`). `DEP003` refuses a compiled vendored distribution, `DEP004` a missing one and a requirement that is neither vendored nor external.

Evidence, all on this branch: full suite `pytest packages/qgis-sdk-python/tests` 2170 passed, 59 skipped, 7 deselected; `tests/scripts` 286 passed plus the four README-mirror rules; `ruff check` clean and `ruff format --check` 406 files; `alint check .` 9/9; new tests `tests/test_external_probe.py` (declaration, metadata, probe incl. every host hint and a QGIS without a message bar), `tests/test_vendoring.py` (real `*.dist-info` fixtures: roots, compiled, missing, transitive, licence/NOTICE, import rewriting in both directions), `tests/test_import_buckets.py` (buckets, DEP001/002, `check --imports`, JSON) and `tests/test_externals_native.py` (2 passed under the real offscreen QGIS 4.2.3: a missing external leaves the plugin unloaded with one message-bar error, a present one constructs the plugin). The build-install harness (`test_bundle_native.py`) still passes with a vendored runtime.

Limits recorded in doc-12: the vendored-import rewrite is textual over import statements, so a package that resolves a dependency by name at runtime (`importlib.import_module`) is out of its reach; a distribution whose metadata cannot be read from the build interpreter is `DEP004`, and the build never installs anything (decision-50 and decision-35 stand).
<!-- SECTION:NOTES:END -->
