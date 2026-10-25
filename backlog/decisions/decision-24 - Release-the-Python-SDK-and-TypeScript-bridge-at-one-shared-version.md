---
id: decision-24
title: Release the Python SDK and TypeScript bridge at one shared version
date: '2026-10-24 15:40'
status: accepted
---
## Context

Two published artifacts ship from this repository: the Python package `qgis-sdk`
(PyPI, conda) and the TypeScript bridge `@archont561/qgis-sdk` (npm, GitHub
Packages). They are not independent products. The bridge mirrors the Python wire
primitives and its contract tests run against the Python declarations, so a
consumer pairs a bridge version with a Python version and expects that pair to be
the one that was tested.

`release.py stamp` has always written a single version into all released
manifests (`pyproject.toml`, the conda `recipe.yaml`, the bridge `package.json`),
so the artifacts were already in lockstep in practice, while
[doc-4](../docs/plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md)
said the opposite: "Only bump packages actually released; SDK/bridge versions and
IPC protocol versions are independent." Two policies, one of them enforced by
tooling and neither enforced by a check.

The milestone plan also moved feature work through minor versions: `.versionrc`
mapped `feat` to a minor bump, so any feature landed mid-milestone would advance
the public minor before the milestone it belonged to was finished.

## Decision

**One package version for both artifacts.** Every release stamps and publishes the
same `major.minor.patch` for `qgis-sdk` and `@archont561/qgis-sdk`, and
`release.py verify-versions` refuses a workspace whose released manifests
disagree. The release workflow runs that check immediately after stamping, so a
divergence fails the build instead of being discovered by a consumer.

**Minor is the milestone axis; patch is everything else.** `.versionrc` now maps
`feat` to a patch bump as well as `fix`. Within a milestone, any number of feature
and fix releases stay on the same minor. The minor advances when:

- a **breaking change** lands (`feat!:` or a `BREAKING CHANGE` footer) - which
  pre-1.0 is a minor bump, the standard 0.x reading; or
- the **milestone closes**, by passing the version explicitly
  (`release.py plan --bump minor` or `--version-override X.Y.Z`).

The milestone release is therefore deliberate and recorded, never inferred from
the commit stream. Automatic derivation answers "what changed since the last
release", which is the wrong question at a milestone boundary.

**Wire protocol versions stay independent.** `PluginDescription.schema_version`,
the bridge contract version and any future IPC protocol version describe
compatibility of the transport, not of the packages. They are not stamped by the
release tool and must not be coupled to the package version.

**The scoped tags stay, with a narrow meaning.** `python-v*` and `ts-v*` exist and
`release.py classify --scoped` reports which registries a tag publishes to. A
scoped release means "publish only this side"; it still stamps both manifests, so
the shared version invariant holds. It is for an out-of-band fix in one artifact,
and the changelog entry must say so.

## Consequences

- A consumer can read one version and know which pair was tested together.
- npm version space is consumed by every release, including one that only
  changed Python code, because npm versions are immutable. This is the accepted
  cost of the invariant; the scoped tag does not avoid the stamp, only the
  publish.
- Feature releases look like patches before 1.0.0. Additive API growth is
  therefore documented in the changelog (`Features` stays visible and is not
  hidden), which is where a reader looking for "what is new" already goes.
- `release.py plan` no longer proposes a minor bump for feature work: on a branch
  full of feature commits it proposes a patch. Releasing a milestone without
  saying so would understate the change, so TASK-28 requires the explicit bump.
- The invariant is enforced in three places: `verify-versions` locally, the same
  task in the build job of `release.yml`, and tests that pin the repository's real
  `.versionrc` and manifest agreement.
- Reversing this later is a policy change, not a config tweak: it would need a
  new decision, because doc-4, TASK-28 and the release workflow all cite this one.

## Superseded 2026-10-24

This decision was replaced the same day it was implemented, before any release
shipped under it. [decision-25](decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)
keeps the bump policy - patches inside a milestone, an explicit minor at the
close - and drops the shared number: each package versions independently, and a
shared plugin-description contract version is what holds a pair together.

The reason is the cost listed below: a shared number forced npm releases whose
tarball was identical to the previous one, and made every release gate verify an
artifact nobody had changed. decision-25's Context records the measurement.

Read decision-25 for current policy. This file stays as the record of how the
workspace arrived there, including the costs that motivated the switch.
