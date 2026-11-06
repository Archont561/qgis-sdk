---
id: TASK-90
title: Prepare and qualify 0.10.0 release
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-06 19:45'
labels: []
milestone: m-9
dependencies:
  - TASK-83
  - TASK-85
  - TASK-86
  - TASK-87
  - TASK-88
  - TASK-89
type: chore
ordinal: 90000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the services II release (m-9, decision-54), not evidence of release or permission to publish. Python 0.10.0 paired with a bridge minor carrying the regenerated host manifest.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name.
- [x] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [x] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [x] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks. (Approved with "publish" after the green `-rc.1` rehearsal; released as `python-v0.10.0` and `ts-v0.7.0` on `71e6b62`, recorded in doc-14 under "Released afterwards".); no stable 1.0.0 promise, automatic publication or invented passing checks.
- [x] #5 The bridge pair is confirmed with evidence: the next @archont561/qgis-sdk minor (regenerated generated/host.ts, HOST_FINGERPRINT moved, HOST_SCHEMA_VERSION and BRIDGE_PROTOCOL_VERSION unchanged) is gated in the same run and tagged on the same merge commit only on the same explicit authorization; release.py verify-versions agrees on the contract version in both languages; doc-22 shows every 0.10.0 service complete. (The values this minor ships are
`HOST_SCHEMA_VERSION` 1 and `BRIDGE_PROTOCOL_VERSION` 2: the protocol moved to 2
earlier in the train, with the stream `ack`, and neither moved in this gate - see
the notes below.)
<!-- AC:END -->

## Released (2026-11-06)

Owner said "publish", after the gate merged as `71e6b62` (PR #170) and the
`-rc.1` pair had run green on that commit. Two annotated tags on the same
commit, one authorization for both scopes because this minor releases the
bridge with the kit:

- `python-v0.10.0` (run 42280008092) - `build`, `pypi`, `conda` and
  `github-release` succeeded; `npm`, `ui`, `github-packages` and
  `github-packages-ui` skipped. The three PyPI uploads, the three prefix.dev
  uploads and the GitHub Release were real; the prerelease skip steps were
  themselves skipped.
- `ts-v0.7.0` (run 42280008166) - `build`, `npm`, `github-packages` and
  `github-release` succeeded; `pypi`, `conda`, `ui` and `github-packages-ui`
  skipped. "Publish to npm", "Publish the alias to npm" and "Publish to GitHub
  Packages" all ran.

PyPI serves 0.10.0 as `latest` for `qgis-sdk`, `qgis-sdk-runtime` and
`qgis-sdk-tools` (`83ea762f`, `b3cc3a32`, `3d3af62e`), the same three wheel
digests this gate built and checked locally. npm serves
`@archont561/qgis-sdk` 0.7.0 as `latest` and its alias `qgis-sdk` at 0.7.0, and
the packed tarball carries `HOST_FINGERPRINT` `sha256:9aa12425...`, the value
the Python side declares. A fresh CPython 3.11.2 venv installing the published
`qgis-sdk[mcp]==0.10.0` resolves `mcp 2.3.0` + `mcp-types 2.3.0` with a clean
`pip check`, renders `qgis-sdk mcp --help`, and scaffolds a server project with
`>=0.10,<0.11` windows that `check` passes.

Both GitHub Releases are stable, carrying the three wheels and three `.conda`
files with `SHA256SUMS` (Python) and the two `.tgz` files with `SHA256SUMS`
(bridge). All five criteria are checked and the task is Done. The prefix.dev and
GitHub Packages uploads are attested by the run logs; Conda and the native QGIS
rows remain outside this sandbox.

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate run on this branch, built on `main` `7eed0a9` (the PR #169 merge), opened
as PR #170, and recorded in doc-14 under "0.10.0 release gate (2026-11-06)". The stamp is in
this pull request; the gate itself spends nothing.

AC 1 (evidence, migration notes). Pure Python suite 2686 passed / 107 skipped /
7 deselected at the unstamped head and 2692 / 106 / 7 on the stamped tree,
`tests/scripts` 305 passed - after `pyyaml` was installed, because the rebuilt
`venv` had none and the first run's nine failures were all
`ModuleNotFoundError: yaml`, `test_ci.py` and the seven UI-publish-shell tests
included. Ruff clean and formatted over 510 files, Biome 196 files, Alint 9/9,
gherlint 9 feature files, both examples green through the installed
`qgis-sdk test` (26 passed / 8 deselected and 8 passed) and clean through
`check` (11 and 3 files). doc-12 gained `## 0.10.0 migration notes` and doc-13
`## 0.7.0 migration notes`, both final and covering every name the services
added or changed - the `LayerInfo` union, `VectorLayerInfo.kind`,
`FakeProject`'s module, the four capabilities and their refusals, every model,
schema constant, error and fake, the grant vocabulary's twelve new names
against the ten already published, `@tool`/`start`, protocol-2 `ack` and `gap`,
`readBlob`, `followSubscription` - plus a 0.9-project checklist. The docs build
and its link check are Bun jobs: not run here, carried by `build-and-check-site`.

AC 2 (version policy and manifests). `plan` answers `python-v0.10.0` from
`python-v0.9.0` and `ts-v0.7.0` from `ts-v0.6.0`; `classify` accepts both
stable tags and both `-rc.1` prereleases (`0.10.0rc1`, `0.7.0rc1`). The stamp
moved the kit, runtime and tools to 0.10.0 with the kit's three exact pins, the
tools' runtime range to `>=0.10.0,<0.11`, the recipe's three versions and both
examples' windows; `--scope typescript 0.7.0` moved the bridge manifest, the
alias and its pin and `SDK_NPM_VERSION`. By hand: the components' and their
alias's peer range to `>=0.7.0 <0.8.0`, the one `SDK_NPM_VERSION` literal in
`test_scaffold_web.py`, the root and five package README status lines.
`verify-versions` agrees on 0.10.0 / 0.7.0 / 0.1.0 with the peer range holding
the bridge, and on contract version 1 in both languages.

AC 3 (compatibility, licences, generated files, installation). Regenerating the
bridge clients changed nothing and `bridge generate --check` is up to date; the
three 0.10.0 wheels build, twine-check and pass `verify-python` with `LICENSE`
in `dist-info/licenses`; a fresh 3.11.2 `venv` installs them `--no-index` into
10 clean distributions (`pip check` clean) and scaffolds
`>=0.10,<0.11`/`>=0.10,<0.11` with `check` clean; the same scaffold moved to
`>=0.9,<0.10` is read as `VERSION001` + `VERSION004` with their remediations
instead of crashing.

AC 5 (the bridge pair). `HOST_FINGERPRINT` moves to
`sha256:9aa12425fcbffd493608456671505acf0eb625ee4cb91f391d2a9bc84b2c5c56`,
`HOST_SCHEMA_VERSION` stays 1, `BRIDGE_PROTOCOL_VERSION` stays 2 (it moved to 2
earlier in the train, with the stream `ack`, not in this gate), and the
catalogue behind the fingerprint is 63 operations / 22 grants / 9 destructive.
doc-22 shows every 0.10.0 service complete, with the payload and vocabulary rows
corrected to say what landed rather than what was planned;
`test_service_coverage.py` passes.

The pull request's eight rows are green on `4bf3b6f`; the first attempt's
`Linux coverage` failed once on `test_plugin_http_limits.py`'s 64-session
budget while `Linux checks` ran the same file green on the same commit, and
the lane passed on the next run - recorded in doc-14 as load-sensitive, not
as a defect this gate fixed.

Rehearsal (2026-11-06). The gate merged as `71e6b62` (PR #170) and the owner's
"do rehearsal and merge" cut one prerelease tag per scope on that commit:
`python-v0.10.0-rc.1` (run 42278465791) and `ts-v0.7.0-rc.1` (run 42278466448),
both entirely green. The Python run stamped `0.10.0-rc.1`, verified the stamped
manifests and the shared contract, built three wheels and three Conda outputs,
verified the wheel without uploading, skipped the prefix.dev upload for a
prerelease and published a GitHub prerelease; npm, ui and both GitHub Packages
jobs skipped. The bridge run stamped `0.7.0-rc.1`, built the bridge, packed the
bridge and alias tarballs with the alias smoke install, dry-ran the npm publish
and the GitHub Packages publish, and published its prerelease; pypi, conda and
the ui jobs skipped. Nothing was consumed: PyPI still serves 0.9.0 as `latest`
for the three distributions and npm still lists `@archont561/qgis-sdk` at 0.6.0
with no 0.7.0 at all. Recorded in doc-14 under "0.10.0 rc rehearsal
(2026-11-06)".

AC 4 stays open on purpose. This pull request records the artifacts and the
checks and posts no date for 1.0.0; nothing is tagged and nothing is uploaded.
`python-v0.10.0` and `ts-v0.7.0` - or the `-rc.1` pair first - are cut on one
explicit "publish", on the merge commit of the stamp pull request, and both
scopes ride that one authorization because this minor releases the bridge.
<!-- SECTION:NOTES:END -->
