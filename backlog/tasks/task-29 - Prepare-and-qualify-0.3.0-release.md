---
id: TASK-29
title: Prepare and qualify 0.3.0 release
status: Done
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T11:25:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-4
  - TASK-5
  - TASK-7
  - TASK-15
  - TASK-17
  - TASK-18
  - TASK-20
  - TASK-28
references:
  - doc-8
priority: high
type: chore
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required 0.3.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [x] #2 Use valid SemVer and prereleases (0.3.0-alpha.1 for Python, 0.2.0-alpha.1 for the bridge); release each package under its own tag at its own explicitly advanced minor — `python-v0.3.0` and `ts-v0.2.0` — verify both scopes plus the shared contract version, and document migration notes per package.
- [x] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [x] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-25: publishing approval given in the session ('publish new versions'). Plan: stamp python 0.3.0 and typescript 0.2.0 on the session branch with migration notes, verify both scopes and the shared contract, build wheel/conda/bridge locally, merge, then cut python-v0.3.0 and ts-v0.2.0 as explicit acts.

2026-10-25 (stamped, not yet tagged):
- AC #1: every dependency is Done (TASK-4, 5, 7, 15, 17, 18, 20, 28), each closed in its own merged PR with CI evidence; the last, TASK-7, merged as PR #62 at e1665dd with checks, macOS and Windows green.
- AC #2: 'release.py stamp --scope python --version 0.3.0' wrote pyproject.toml and recipe.yaml; 'stamp --scope typescript --version 0.2.0' wrote the bridge package.json. 'release.py plan' (dispatch trigger, dry run) plans python-v0.3.0 from python-v0.2.0 and ts-v0.2.0 from v0.1.1. Migration notes: doc-12 '0.3.0 migration notes', doc-13 '0.2.0 migration notes'. A public-signature diff of src/qgis_sdk between python-v0.2.0 and HEAD removes nothing and only adds defaulted fields; the bridge root entry removes no export.
- AC #3: 'verify-versions' passes for both scopes and reports plugin description contract version 1 agreeing across the two languages; BRIDGE_PROTOCOL_VERSION and HOST_SCHEMA_VERSION stay 1. Wheel qgis_sdk-0.3.0 builds, passes twine check, ships LICENSE (MIT) and no tests/scripts; a clean venv install reports 0.3.0, imports bridge/network/jobs/testing/webengine without qgis in sys.modules and exposes the qgis-sdk CLI. 'npm pack' of the bridge is 15 files (dist, README, LICENSE, package.json) at 0.2.0; installed from the tarball, all five entry points resolve (./react only with the optional react peer, as documented). generate_bridge_clients.py --check up to date. Gates: lint-python, format-python-check, actionlint, typecheck, biome clean; bun run test 1113 passed/33 skipped; coverage Python 97.15%, bridge 96.49/98.12; tests/scripts 174 passed. The conda build needs conda-forge, which this sandbox cannot reach; release.yml builds it on the tag, as for 0.2.0.
- AC #4 stays open until the tags exist and the registries answer.

2026-10-25 (released): approval 'publish new versions' in the session.
- Stamp PR #63 merged into main at 0cf8a99 (checks, macOS, Windows green). The sandbox token cannot dispatch workflows (403, as for 0.2.0), so both annotated tags were created on 0cf8a99 and pushed directly: python-v0.3.0 ('qgis-sdk 0.3.0') and ts-v0.2.0 ('qgis-sdk-bridge 0.2.0'), each carrying the plan's changelog. release.py classify reads them as clean, single-scope releases.
- python-v0.3.0, release run 40156889218: build, pypi, conda and github-release succeeded; npm and github-packages skipped (python scope). PyPI qgis-sdk reports 0.3.0 as latest; GitHub Release python-v0.3.0 carries qgis_sdk-0.3.0-py3-none-any.whl, qgis-sdk-0.3.0-pyh4616a5c_0.conda and SHA256SUMS; the prefix.dev upload job succeeded.
- ts-v0.2.0, release run 40156890964: build, npm and github-packages succeeded - npm reports @archont561/qgis-sdk-bridge 0.2.0 (shasum 0a6f4f67f530bf3b8d605ba2ed3fd6d25789253f, with provenance) - but github-release failed: a TypeScript-only tag downloads no wheel, dist/ never exists, and release-checksums could not write dist/SHA256SUMS. Fixed in this branch (write_checksums creates the directory, test added, workflow mkdir). The GitHub Release ts-v0.2.0 was created from the tag annotation with the same tool; its assets could not be uploaded from the sandbox (uploads.github.com is unreachable here). Remaining act: once the fix is on main, dispatch release.yml with tag=ts-v0.2.0 - npm and GitHub Packages skip the existing version and github-release attaches archont561-qgis-sdk-bridge-0.2.0.tgz (sha256 1ceff5ad2c8f327a8043e4ab96c40427e014dd0722f8fc6c5f77272dcd07ee8c) and SHA256SUMS.
- AC #4 stays open until that release carries its assets.

Closed 2026-10-25 (doc-16 hygiene). Artifacts and approval recorded above: python-v0.3.0 and ts-v0.2.0 published under explicit owner authorization, checks named per run. The ts-v0.2.0 GitHub Release still carries no assets; attaching them is a release.yml dispatch with tag=ts-v0.2.0 and is optional now that @archont561/qgis-sdk-bridge is deprecated in favour of @archont561/qgis-sdk 0.3.0 (TASK-55).
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---

author: qgis-sdk agent
created: 2026-10-24 16:25
---
AC #2 amended on 2026-10-24, before any criterion was checked: decision-25 split the versions. This gate now covers two releases made from the same milestone - python-v0.3.0 and ts-v0.2.0 - each with its own explicit minor and its own scope check, plus the shared plugin-description contract version. The two numbers are not expected to match.
---
<!-- COMMENTS:END -->
