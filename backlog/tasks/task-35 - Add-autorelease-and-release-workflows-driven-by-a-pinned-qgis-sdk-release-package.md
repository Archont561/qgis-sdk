---
id: TASK-35
title: >-
  Add autorelease and release workflows driven by a pinned qgis-sdk-release
  package
status: Done
assignee: []
created_date: '2026-10-17 20:20'
updated_date: '2026-10-17 21:52'
labels: []
milestone: m-3
dependencies: []
references:
  - .github/workflows/publish-sandbox.yml
  - pixi.toml
  - .versionrc
  - >-
    backlog/decisions/decision-3 -
    Development-and-distribution-artifacts-are-separate.md
  - backlog/tasks/task-8 - Build-a-validated-QGIS-installable-plugin-ZIP.md
  - backlog/tasks/task-9 - Define-SDK-and-plugin-release-compatibility-gates.md
  - packages/qgis-sdk-python/pyproject.toml
  - packages/qgis-sdk-typescript/package.json
priority: medium
type: chore
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Mirror the pixi-sandbox operating model for releases. The publish-sandbox.yml pattern today: a version-pinned external CLI (pixi-sandbox==0.7.0 from a dedicated channel), a checksum-verified bootstrap (fetch-release), one cross-platform pipeline command that packs, verifies and publishes, generated owned files, and a weekly upgrade job that touches only owned files. This task builds the release-side equivalent: a separate qgis-sdk-release repository/package that encapsulates all release logic and publishes checksummed releases; qgis-sdk pins an exact version. Two workflows are added - autorelease.yml (on push to main: derive the next SemVer version and changelog from conventional commits per .versionrc/convco, then open or update a release PR or push a tag) and release.yml (on that tag: build, verify, and publish artifacts - the qgis-sdk Python wheel via the pinned python-build/hatchling/twine stack, the qgis-sdk-bridge npm package, the plugin ZIP once TASK-8 lands, and a GitHub Release with SHA256SUMS). Every workflow step invokes the tool through pixi run tasks wired in pixi.toml (a dedicated release feature/environment pinning qgis-sdk-release) so local runs and CI runs share the exact same entrypoints. Decision-3 holds: development and distribution artifacts stay separate. Registry publishing is decided and provisioned: OIDC trusted publishing binds the PyPI project qgis-sdk and the npm package qgis-sdk-bridge to the workflow release.yml with the GitHub environments pypi and npm - so the release workflow file must be named release.yml and its publish jobs must run under exactly those environments with id-token: write and no long-lived registry tokens. The SDK-plugin compatibility gates (TASK-9) stay sequenced behind their own explicit decision. Non-goals: building the plugin ZIP itself (TASK-8), defining compatibility gates (TASK-9), changing what CI tests (TASK-34 scope).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The release tool lives in packages/qgis-sdk-release as a stdlib-only Python CLI with its own pytest suite (in-repo per the 2026-10-17 user decision; the workflows consume it exclusively through pixi run tasks) - extraction into a standalone checksum-pinned repository is tracked as TASK-36
- [x] #2 All release logic is invoked from the workflow ymls through pixi run tasks declared in pixi.toml (a dedicated release feature/environment) and the identical task invocations work locally from a restored sandbox
- [x] #3 autorelease.yml on push to main derives the next SemVer version and changelog from conventional commits per .versionrc (convco-compatible); the push trigger never tags while no STABLE tag exists - bootstrap and the first stable release are deliberate workflow_dispatch acts, optionally with a prerelease suffix that continues the rc train - and it continues the train automatically once a stable tag exists, demonstrated on real main merges
- [x] #4 release.yml on a release tag builds and verifies artifacts - the qgis-sdk Python wheel (hatchling backend already pinned) and the qgis-sdk-bridge npm package - and publishes a GitHub Release with SHA256SUMS; the plugin ZIP is wired in when TASK-8 lands
- [x] #5 Registry publishing runs under the provisioned OIDC trusted publishing bindings - PyPI project qgis-sdk and npm package qgis-sdk-bridge both bound to workflow release.yml with GitHub environments pypi and npm respectively; publish jobs run under exactly those environments with id-token: write and no long-lived registry tokens or secrets, and prerelease tags dry-run both registries instead of uploading
- [x] #6 Workflows pass actionlint, use SHA-pinned node24 actions, and follow the TASK-34 conventions (concurrency groups and dependency caching); the task closes with evidence of one full autorelease-then-release cycle on a test tag (run URLs and artifact checksums)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Created 2026-10-17 at user request: autorelease and release workflows just like pixi-sandbox, with a separate qgis-sdk-release repo/package called from pixi run tasks in the workflow ymls. Pattern sources: publish-sandbox.yml (pinned CLI, checksum-verified fetch-release bootstrap, single cross-platform pipeline command, owned-files upgrade job) and scripts/restore.sh + pixi-sandbox.toml (reviewed config, generated owned files). Existing release-relevant assets: .versionrc (conventional-commit versioning, semver, initialBumpVersion 0.1.0), convco 0.7.2 + lefthook in the utils feature, python-build/twine/hatchling pinned in the python feature. Milestone m-3 chosen because release automation is developer-workflow + packaging infrastructure; move it earlier if a release train needs it before 0.4.0.

2026-10-17 update: the user provisioned OIDC trusted publishing before implementation - PyPI project qgis-sdk bound to workflow release.yml with GitHub environment pypi, and npm package qgis-sdk-bridge bound to workflow release.yml with environment npm. Hard constraints inherited: the release workflow file must be named release.yml, and the publishing jobs must declare environment: pypi / environment: npm with permissions id-token: write; no registry secrets are needed or wanted. Verified workspace identities: packages/qgis-sdk-python/pyproject.toml declares name qgis-sdk with hatchling==1.32.4 build backend; packages/qgis-sdk-typescript/package.json declares qgis-sdk-bridge 0.1.0. Implementation checks to settle during the work: pick publish clients that actually support OIDC trusted publishing - pypa/gh-action-pypi-publish (or twine with an exchanged short-lived token) for PyPI; for npm confirm whether the pinned Bun 1.4.2 bun publish supports npm trusted publishing and otherwise provide npm CLI >= 11.5.1 in the release environment. The qgis-sdk wheel must build from packages/qgis-sdk-python while the dev flow stays on PYTHONPATH (AGENTS.md forbids a path/editable Pixi extra).

2026-10-17 implementation decisions (user-approved): tool stays in-repo at packages/qgis-sdk-release (TASK-36 tracks extraction); registries are gated to clean vX.Y.Z tags with prerelease dry-runs; the push-to-main trigger refuses to create the first tag so the initial 0.1.0 stays a deliberate TASK-27 act bootstrapped via workflow_dispatch. Pins chosen for the workflows: npm@12.2.0 (OIDC needs >= 11.5.1; bun publish support unverified so the npm job uses the npm CLI under setup-node v7.1.0/node 24), pypa/gh-action-pypi-publish v1.14.2, setup-pixi v0.11.2 with pixi-version v0.81.0, checkout v7.0.1, upload/download-artifact v7.0.2/v8.0.2, actions/cache v6.1.0 - all SHA-pinned. Release tasks live in the existing python feature with a task-level PYTHONPATH, so pixi.lock stays untouched (pixi lock --check green locally).

Evidence cycle (2026-10-17). Landed: PR #17 merge 2c7d0a6 (tool + workflows + wiring), PR #18 merge dc7fd83 (pypi-job checkout + npm prerelease dist-tag fixes), PR #19 merge 296f54c (stable-tag push guard). Test-tag cycle: v0.1.0-rc.2 on dc7fd83 -> release run 39071817646, all four jobs green (build/pypi/npm/github-release) -> GitHub Release https://github.com/Archont561/qgis-sdk/releases/tag/v0.1.0-rc.2 flagged prerelease with assets qgis_sdk-0.1.0rc2-py3-none-any.whl (23575 B), qgis-sdk-bridge-0.1.0-rc.2.tgz (997 B), SHA256SUMS (198 B). Registries provably untouched: PyPI qgis-sdk serves only the pre-existing 0.0.0 placeholder (uploaded 2026-10-15, before this work); npm qgis-sdk-bridge 404s (first clean publish will create it). Push-trigger guard runs on real merges: 39071033736 and 39071805458 (no tags yet), 39072369532 (prerelease-only history + a release-worthy fix commit -> computed v0.1.1 then skipped; git ls-remote shows no new tag). The evidence runs caught two real bugs, both fixed in follow-up PRs: pypi job missing checkout + npm refusing prerelease publishes without --tag even for dry runs (rc.1 run 39071399382, reproduced locally with npm 12.2.0 under bun), and the rc bootstrap arming clean publishes (fixed by the stable-tag guard). Caveats: the workflow_dispatch trigger itself could not fire from the sandbox (the GitHub integration lacks actions:write, HTTP 403) - the dispatch plan/tag path was exercised locally through the identical pixi tasks and the rc.2 tag was created with the same tool invocations; the first genuine OIDC upload happens at the first clean tag (deliberate, TASK-27); release asset re-download from the sandbox is blocked by the blob host, so SHA256SUMS verification evidence is runner-side.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
TASK-35 delivered the release train: a stdlib-only qgis-sdk-release CLI (76 pytest tests) in packages/qgis-sdk-release, nine release-* pixi tasks in the existing python feature (pixi.lock untouched, lock guard green on every PR), autorelease.yml (push-to-main SemVer/changelog planning from .versionrc with the deliberate-first-stable-release guard, dispatch bootstrap with optional rc suffix), and release.yml (tag-triggered: stamp -> wheel via python-build/hatchling + twine check -> bridge via bunup -> GitHub Release with SHA256SUMS; PyPI via pypa/gh-action-pypi-publish under environment pypi and npm via npm@12.2.0 under environment npm, both id-token: write OIDC trusted publishing, both dry-run for prereleases). All actions SHA-pinned on node24 runtimes; concurrency and caching per TASK-34; qgis-sdk-bridge un-privated for npm. Proven end-to-end on the v0.1.0-rc.2 cycle (release run 39071817646 green, prerelease GitHub Release with wheel+tarball+SHA256SUMS, registries untouched) and on three autorelease guard runs across real main merges. Real 0.1.0 to PyPI/npm stays a deliberate dispatch act for TASK-27; standalone-repo extraction is TASK-36.
<!-- SECTION:FINAL_SUMMARY:END -->
