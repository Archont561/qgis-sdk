---
id: decision-25
title: Version each package independently behind a shared contract version
date: '2026-10-24 16:24'
status: accepted
---
## Context

[decision-24](decision-24%20-%20Release-the-Python-SDK-and-TypeScript-bridge-at-one-shared-version.md)
made this repository release one shared `major.minor.patch` for the Python package
and the TypeScript bridge, enforced by `release.py verify-versions`. It was
accepted and implemented on 2026-10-24, and it fixed a real inconsistency: the
tooling had always stamped one version into every manifest while
[doc-4](../docs/plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md)
claimed the artifacts versioned independently.

Working with it for a single milestone exposed where the cost lands - on the
bridge:

- **The bridge has nothing to release in 0.2.0.** Between `v0.1.1` and the
  branch that closes m-1, `packages/qgis-sdk/` gains about 2,200 lines across 31
  files and `packages/qgis-sdk-bridge/` gains zero. A shared number publishes a
  bridge version whose tarball is identical to 0.1.1, and npm versions are
  immutable.
- **Every release gate has to verify an unchanged artifact.** The 0.2.0
  milestone definition ended up stating that the bridge is built, packed and
  checked "even though nothing changed" - a policy compensating for a policy.
- **The number stops carrying information.** Pre-1.0 consumers read a version to
  decide whether to upgrade. A version that never differs from its predecessor
  teaches them to ignore it.

What the shared number bought was exactly one thing: the pair is provable from
the numbers alone. That guarantee is worth keeping, but it does not need a
shared number, because the real coupling is a *contract*, not a release train -
the bridge parses the `PluginDescription` that Python generates.

## Decision

**`qgis-sdk` and `@archont561/qgis-sdk-bridge` version independently.** Each
package derives its own `major.minor.patch` from the conventional commits that
touch it - plus the repository-wide files both depend on - starting from its own
last release tag. A release stamps only the manifests of the package it
publishes:

| Tag | Stamps | Publishes |
| --- | --- | --- |
| `python-vX.Y.Z` | `pyproject.toml`, `recipe.yaml` | PyPI, prefix.dev |
| `ts-vX.Y.Z` | `packages/qgis-sdk-bridge/package.json` | npm, GitHub Packages |
| `vX.Y.Z` | all three | both, aligned at one version |

`v*` survives as the deliberate **alignment release**: the way to re-couple the
numbers when that is the clearest thing to say, not the default.

**A shared contract version holds the pair together.**
`PLUGIN_DESCRIPTION_SCHEMA_VERSION` is declared once per language - Python in
`qgis_sdk/declarations.py`, TypeScript in the bridge index - and
`release.py verify-versions` refuses a workspace where the two disagree. The
check runs on every release for every scope, whether or not either package
changed. A change to a serialized shape is therefore either additive (no
contract bump) or bumps the contract in the same change set that ships both
packages.

**The bump policy is unchanged from decision-24.** `feat` and `fix` are patches
inside a milestone, `feat!`/`BREAKING CHANGE` is a minor pre-1.0, and a milestone
close passes its version explicitly. What changed is *which number* moves, not
how it moves.

**A milestone now names a version per artifact.** A milestone that reports no
bridge source change does not release the bridge at all; the Python version still
advances, and the contract check proves the pair is coherent.

## Consequences

- 0.2.0 ships Python `0.2.0` while the bridge stays at `0.1.1`. That is the
  first release under this policy, and the mismatch is the point rather than an
  accident: the bridge surface genuinely did not change.
- No npm version is consumed by a Python-only release. The bridge's next version
  is 0.2.0 in m-2, where its transport, generated clients and React helpers
  actually land.
- A consumer can no longer infer the pair from the numbers. They read the
  contract version, which both packages declare and every release checks, or the
  compatibility statement [TASK-9](../tasks/task-9%20-%20Define-SDK-and-plugin-release-compatibility-gates.md)
  defines in 0.5.0. This is the accepted cost of the change.
- The planner is per scope: `plan --scope python` reads the last python-capable
  tag and only the commits that touch Python (or shared files), so a bridge-only
  feature does not move the Python version and vice versa. `plan` without a
  scope still describes an alignment release.
- `verify-versions` changed meaning: it checks the scoped manifests against the
  version being released plus the contract across languages, instead of demanding
  one number across the workspace. With no arguments it checks every scope on
  its own, which is the invariant that holds at any time.
- Milestone definitions state a version per artifact, and [doc-4](../docs/plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md)
  indexes the bridge delta for each one.
- Only a package's own directory can move its version: a `feat!` in
  `scripts/`, `.github/` or `pixi.toml` changes how a package is built, not what
  it contains, so it triggers nothing. The limit of the rule is conventional
  commits themselves - a single commit touching the release tool *and* a package
  carries one `!` for both, so a policy-breaking commit that also edits package
  source still bumps that package's minor. Keep policy changes in files outside
  `packages/` when that matters.
- Reversing this is a policy change that needs a new decision: doc-4, the
  milestone definitions and TASK-28/TASK-29/TASK-30 all cite this one.

## Implementation (2026-10-24)

- `scripts/release.py`: `sort_tags(scope=...)` and a scope-aware `compute_plan`
  (per-package base tag, path-filtered commits read through
  `git log --format=... --name-only`), `stamp --scope`,
  `verify-versions --scope/--version`, `contract_versions()` and
  `PLUGIN_DESCRIPTION_SCHEMA_VERSION` readers.
- `PLUGIN_DESCRIPTION_SCHEMA_VERSION` is now declared in
  `packages/qgis-sdk/src/qgis_sdk/declarations.py` and used as the default of
  `PluginDescription.schema_version`; the bridge already declared it.
- `.github/workflows/release.yml` stamps and verifies by the tag's scope, so a
  `python-v*` release never touches the bridge manifest.
- [TASK-28](../tasks/task-28%20-%20Prepare-and-qualify-0.2.0-release.md),
  [TASK-29](../tasks/task-29%20-%20Prepare-and-qualify-0.3.0-release.md) and
  [TASK-30](../tasks/task-30%20-%20Prepare-and-qualify-0.4.0-release.md) AC #2
  were rewritten to the per-package rule.
