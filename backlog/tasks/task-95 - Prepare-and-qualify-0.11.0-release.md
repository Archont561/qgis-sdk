---
id: TASK-95
title: Prepare and qualify 0.11.0 release
status: In Progress
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-07 12:30'
labels: []
milestone: m-10
dependencies:
  - TASK-90
  - TASK-91
  - TASK-92
  - TASK-93
  - TASK-94
type: chore
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the layer-kinds, connections, symbology and Processing-breadth release (m-10, decision-54), not evidence of release or permission to publish. Python 0.11.0 paired with a bridge minor carrying the regenerated host manifest; doc-22 complete is the exit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name.
- [ ] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge pair is confirmed with evidence as for 0.10.0, and doc-22 shows every listed area complete or explicitly out of scope by decision. (The values this minor ships with, recorded here so the next gate does not guess: `HOST_SCHEMA_VERSION` 1 and `BRIDGE_PROTOCOL_VERSION` 2; the protocol moved to 2 with the stream `ack` in the 0.7.0 train, and neither moved in this gate - see the notes below.)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate run on this branch, built on `main` `e5e24c8` (the PR #176 merge), opened
as PR #177, and recorded in doc-14 under "0.11.0 release gate (2026-11-07)".
The stamp is in this pull request; the gate itself spends
nothing.

AC 1 (evidence, migration notes). Pure Python suite 2820 passed / 28 skipped
/ 97 deselected at the unstamped head and the same on the stamped tree
(`pytest -c packages/qgis-sdk-python/pyproject.toml
packages/qgis-sdk-python/tests -m pure --ignore
packages/qgis-sdk-python/tests/scripts -n auto`), `tests/scripts` 305
passed and the package scripts lane 111 passed / 1 skipped / 7 deselected.
Ruff clean and formatted over 531 files, Biome 196 files, Alint 9/9 with
the policy suite at 20, gherlint 12 feature files (from the repository
root, where `gherlint.toml` lives), both examples green through the
installed `qgis-sdk test` (26 passed / 8 deselected and 8 passed) and clean
through `check` (11 and 3 files). The first stamped run failed
`test_reference_example.py::test_the_example_declares_the_windows_the_scaffold_writes`
against the throwaway venv's stale editable metadata (0.10.0 baked in at
install time, which is where `sdk_requirements()` reads the windows from);
reinstalling the editable packages refreshed it to 0.11.0 and every lane is
green, which is why the artifact lane installs from built wheels into a
fresh venv instead. doc-12 gained `## 0.11.0 migration notes` and doc-13
`## 0.8.0 migration notes`, both final and covering every name the services
added - the seven-kind `LayerInfo` union and its inputs, the five
`open_*` calls, `ctx.connections` and its models and errors, the renderer,
symbol and labelling models behind `ctx.styles`, `run_model`, `batch` and
`qgis_sdk.batch`, the `layers` output kind and `RunOutput`'s four wire
kinds, `FakeConnections` and the fake additions, and the seven new grant
names against the twenty-two a 0.10 project lists - with a checklist for a
0.10 project and for a 0.7 page.

AC 2 (SemVer, manifests). `release.py plan --scope python --trigger dispatch
--bump minor` answers `python-v0.11.0` "forced release from
python-v0.10.0" and `--scope typescript` answers `ts-v0.8.0` from
`ts-v0.7.0`; `classify` accepts the pair and their `-rc.1` rehearsals
(`0.11.0rc1`, `0.8.0rc1`, `prerelease: true`). `stamp --version 0.11.0
--scope python` moved the kit, runtime and tools to one version with the
kit's exact pins `==0.11.0` (runtime, tools and `tools[mcp]`), the tools'
runtime range `>=0.11.0,<0.12`, the recipe's three versions and both
examples' windows `>=0.11,<0.12`; `--version 0.8.0 --scope typescript`
moved the bridge `package.json`, the alias and its pin, and
`SDK_NPM_VERSION`. By hand: the components' peer range to `>=0.8.0 <0.9.0`
in both the scoped package and its alias, the `SDK_NPM_VERSION` literal in
`test_scaffold_web.py`, and the six README status lines. `verify-versions`
agrees on 0.11.0 / 0.8.0 / 0.1.0 / contract 1. `HOST_SCHEMA_VERSION` 1 and
`BRIDGE_PROTOCOL_VERSION` 2 moved not at all.

AC 3 (artifacts, clean install, previous minor). Three wheels
(`qgis_sdk-0.11.0-py3-none-any.whl`, `qgis_sdk_runtime-0.11.0-...`,
`qgis_sdk_tools-0.11.0-...`) and three sdists build and twine-check -
six artifacts, all PASSED; `verify-python` passes; each wheel carries
`LICENSE` in `dist-info/licenses` and `Requires-Python: >=3.11`. A fresh
CPython 3.11.2 venv installs `qgis-sdk==0.11.0` `--no-index` from
`dist/pypi` over a `typer==0.27.3` + `rich==15.0.0` base: kit, runtime and
tools all 0.11.0, `pip check` clean. Its `qgis-sdk new` writes
`>=0.11,<0.12`, `qgis-sdk check` is clean. The same scaffold with the
windows moved to `>=0.10,<0.11` is read as `VERSION001` (outside the range
this tools release supports, `>=0.11.0,<0.12`) and `VERSION004` (the
importable runtime is 0.11.0), each with its remediation - *checked 3
files: 2 problems*, a report of what changed, not a crash. The native
rows, the smoke and opt-in harnesses, the Bun suites, `check-generated`
(pixi) and Conda are not runnable in this sandbox and are CI-carried.

AC 4 (approval). doc-14's "0.11.0 release gate (2026-11-07)" records every
lane, command and artifact above, including what was not run and where it
is run. Nothing is tagged, nothing is uploaded, and no date is promised for
1.0.0; the pair (`python-v0.11.0` / `ts-v0.8.0`, or their `-rc.1`
rehearsals first) is spent only on explicit authorization - the word
"publish" - on the merge commit of this pull request.

AC 5 (bridge pair, doc-22). `HOST_FINGERPRINT`
`sha256:2c686bb06a3cf63aca219e2a1751a4f00d574472e20ea9cfb52c318bfeed7ec3`
covers 84 operations (79 calls, 5 streams) and 29 grants (14 destructive,
6 credential); the manifest grew 21 operations and 7 grants across the
train, which is what makes the bridge minor mandatory.
`qgis-sdk bridge generate --host --out
packages/qgis-sdk-typescript/src/generated/host.ts --check` reports the
manifest up to date. doc-22's four m-10 rows move to *Shipped* as (0.11.0)
rows and every listed area is complete on what landed, out of scope by
decision, or named with its task and milestone; doc-25 records the train
and this gate.
<!-- SECTION:NOTES:END -->
