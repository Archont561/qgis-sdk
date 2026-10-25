---
id: TASK-55
title: Publish qgis-sdk as an unscoped npm alias of @archont561/qgis-sdk
status: Done
assignee: []
created_date: '2026-10-25 10:34'
updated_date: '2026-10-25 11:07'
labels:
  - release
  - tooling
milestone: m-3
dependencies: []
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner request 2026-10-25: reserve both npm names and make both deploy targets, with the unscoped name as a thin alias. packages/qgis-sdk-alias holds one export-star per entry (., ./bridge, ./host, ./react, ./testing) and a manifest that pins @archont561/qgis-sdk at exactly its own version. scripts/release.py stamps and verifies the alias with the bridge (new manifests 'alias package.json' and 'alias dependency' in the typescript scope; packages/qgis-sdk-alias/ counts as a TypeScript change). release.yml packs both tarballs, smoke-installs them together and imports every non-React entry from both names, publishes the scoped package first and the alias second under the npm environment, and attaches both tarballs to the GitHub Release; GitHub Packages stays scoped-only. Operator runbook: publish a 0.0.0 placeholder per name with setup-npm-trusted-publish, bind release.yml/npm as trusted publisher on both access pages before ts-v0.3.0, then deprecate @archont561/qgis-sdk-bridge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 packages/qgis-sdk-alias re-exports every entry of @archont561/qgis-sdk and its Bun tests fail on any drift in entries, version, pin, files or peers
- [x] #2 scripts/release.py stamp --scope typescript moves the alias version and pin with the bridge, verify-versions names a lagging alias or drifting pin, and alias paths classify as typescript
- [x] #3 release.yml packs, smoke-tests and publishes the alias after the scoped package with provenance, dry-runs both on prereleases, and ships both tarballs in SHA256SUMS; CI and autorelease run the alias tests
- [x] #4 The owner has published the placeholders and bound trusted publishing for @archont561/qgis-sdk and qgis-sdk, and ts-v0.3.0 publishes both names (operator step, recorded when done)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #1-#3 delivered in PR #66 (83412c1, fa2ac33): packages/qgis-sdk-alias with 10 Bun tests, release.py alias stamping/verification (13 tests), release.yml pack + tarball smoke + ordered publish + SHA256SUMS, CI and autorelease run the alias tests. Smoke verified locally against the real tarballs (12/12/22/4 exports mirrored). AC #4 is the owner's step: npx setup-npm-trusted-publish for @archont561/qgis-sdk and qgis-sdk, then bind release.yml / environment npm on both access pages before ts-v0.3.0. Stays In Progress until that is recorded.

2026-10-25 release prep: owner confirmed the placeholders (0.0.0 on @archont561/qgis-sdk and qgis-sdk, registry shows both created 10:45 UTC) and the trusted-publisher bindings for release.yml / environment npm. Stamped 0.3.0 for scope typescript (scoped manifest, alias manifest and its pin; bun.lock refreshed) with doc-13's 0.3.0 migration notes, as the ts-v0.3.0 stamp PR. release.py plan --version-override 0.3.0 reads ts-v0.3.0 (forced minor: feat is a patch pre-1.0; decision-33 fixes the first publish under the new name at 0.3.0). The tag is pushed on the merge commit after the PR lands; AC #4 is checked once release.yml has published both names.

Published 2026-10-25 11:05 UTC from tag ts-v0.3.0 on merge commit f8d3946 (PR #67), release run 40187356756: build, smoke (both tarballs), npm and github-packages succeeded. Registry: @archont561/qgis-sdk 0.3.0 latest (shasum 7593c0d12ee3c8e76424417e324c3451b33d5097, provenance attestations) and qgis-sdk 0.3.0 latest (shasum 858d7f23e9e86ed5989ef9d00db66f81c4e5449c, provenance attestations, depends on @archont561/qgis-sdk 0.3.0). Trusted publishing worked for both names on the first run. The github-release job failed before creating the release (npm/*.tgz glob missed the two-directory artifact); the Release ts-v0.3.0 was created from the sandbox with release-github (notes only). Fix daac5e9 globs npm/*/*.tgz; after it lands, dispatching release.yml with tag=ts-v0.3.0 attaches both tarballs and SHA256SUMS (publishes skip existing versions).
<!-- SECTION:NOTES:END -->
