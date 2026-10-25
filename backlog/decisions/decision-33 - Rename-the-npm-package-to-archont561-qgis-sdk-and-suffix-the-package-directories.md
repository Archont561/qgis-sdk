---
id: decision-33
title: Rename the npm package to @archont561/qgis-sdk and suffix the package directories
date: '2026-10-25 20:30'
status: accepted
---
## Context

The TypeScript package was published as `@archont561/qgis-sdk-bridge` from
`0.1.0` through `0.2.0` and lived in `packages/qgis-sdk-bridge`, next to the
Python package in `packages/qgis-sdk`. The name described the first thing it
shipped: the wire contract and the transport client. By `0.2.0` it already
carried four entries (`.`, `./bridge`, `./host`, `./react`) plus `./testing`,
and the owner said on 2026-10-25 that "bridge" had become limiting because the
same package is where web-view UI building blocks will ship. Two names for two
halves of one SDK, one of them narrower than its contents, also made the
directory pair asymmetric: `qgis-sdk` was the Python directory and the PyPI
distribution, while the TypeScript directory needed a qualifier.

## Decision

1. **One SDK name on both registries.** The npm package is
   `@archont561/qgis-sdk`, the counterpart of the PyPI distribution
   `qgis-sdk`. Capability lives in subpath entries, not in the package name:
   `./bridge`, `./host`, `./react`, `./testing` today, `./ui` and others when
   they exist, each importable on its own with optional peers
   (`react >= 18` only for `./react`).
2. **Directories carry a language suffix.** `packages/qgis-sdk-python` holds
   the Python package and `packages/qgis-sdk-typescript` the TypeScript
   package. The suffixes match the release scopes (`python`, `typescript`)
   and the tag prefixes (`python-v*`, `ts-v*`) from decision-25, which do not
   change. The Python distribution name `qgis-sdk` and the import module
   `qgis_sdk` (including `qgis_sdk.bridge`) do not change either.
3. **The rename is a release of the same surface.** `@archont561/qgis-sdk`
   ships first as `0.3.0`, the next version after the last
   `@archont561/qgis-sdk-bridge` (`0.2.0`), with no export change; the
   version counter continues rather than restarting, so a consumer swapping
   the name reads a monotonic history. `scripts/release.py` keeps
   `qgis-sdk-bridge` as a legacy scope alias and adds `qgis-sdk-python` and
   `qgis-sdk-typescript`.
4. **Old name, deprecation only.** After the first publish under the new
   name, the owner deprecates `@archont561/qgis-sdk-bridge` on npm with a
   message pointing at `@archont561/qgis-sdk`; nothing is unpublished.
5. **The backlog uses the current name throughout**, except where a closed
   task records a published artifact (a tag annotation, a tarball name, an
   `npm view` result, the trusted-publishing binding as provisioned). Those
   lines stay as written, because they are evidence of what was shipped.

## Consequences

- Trusted publishing is per package name. The npm OIDC binding provisioned
  for `qgis-sdk-bridge` (TASK-35) does not cover `@archont561/qgis-sdk`; the
  owner provisions a new trusted publisher (workflow `release.yml`,
  environment `npm`) before the first `ts-v0.3.0` tag. Until then a
  TypeScript release tag would fail in the `npm` job, not silently publish
  the old name.
- The `ts-v0.2.0` GitHub Release remains the last artifact of the old name;
  its outstanding asset dispatch (TASK-29) is unaffected.
- Coverage flags become `qgis-sdk-python` and `qgis-sdk-typescript`; the
  Codecov history under the old flags is not migrated.
- Workspace tooling (Pixi tasks, Turbo filters, CI workflows, generators,
  tests) refers to the new paths and name; the generated TypeScript clients
  are structural and did not change.
