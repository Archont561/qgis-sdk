---
id: decision-36
title: Cut the three Python distributions before the contract freeze
date: '2026-10-25 17:40'
status: accepted
---
## Context

[decision-35](decision-35%20-%20Split-the-Python-SDK-into-a-runtime-a-tools-package-and-a-meta-kit-behind-one-contract.md)
sequenced the split in two steps and tied step 2 - the three distributions,
the release scopes, the per-distribution publish steps and the multi-output
recipe - to "the contract freeze", a separate decision at which
`PluginContext`, the service protocols, the description schema and the
bridge protocol stop moving between minors. Step 1 (the tree split inside
one wheel) landed in 0.4.0 (TASK-56, PR #73).

Revisiting the gate after 0.4.0 shipped showed it was the wrong coupling:

- **The gate protected a number, not the user.** What a freeze changes is
  the *major* of `qgis-sdk-runtime`: a frozen contract is the 1.0 promise.
  Nothing about publishing three 0.x wheels needs the contract frozen; the
  runtime at 0.5 may still move between minors and says so.
- **Waiting costs more each release.** Every 0.x release before the split
  publishes a `qgis-sdk` wheel whose users then have to migrate (the kit's
  base install stays the same, but console users and anyone pinning the
  runtime range learn the new names later). The code boundary already
  exists and is enforced by the layer test; only the packaging lags.
- **The names are reserved and idle.** `qgis-sdk-runtime` and
  `qgis-sdk-tools` sit on PyPI at placeholder `0.0.0` with trusted
  publishing bound to `release.yml` / environment `pypi` since
  2026-10-25. A placeholder that stays empty for a milestone is a liability.
- **The 0.5.0 work wants the boundary.** TASK-9 (compatibility gates)
  needs to state which runtime a tools release tested against; that
  statement is a dependency range on a real distribution or it is prose.

## Decision

Decision-35's step 2 is decoupled from the contract freeze and executes in
the 0.5.0 development line (m-4, TASK-57). The freeze keeps its own future
decision; its effect is now defined as **the runtime's 1.0.0**, not as the
moment the distributions appear.

Until the freeze, the three distributions follow decision-35's rules with
one simplification: they release **together under the existing `python`
scope at one version**. `release.py stamp --scope python` writes the kit,
the runtime and the tools manifests, re-pins the kit (`qgis-sdk-runtime==X`,
`qgis-sdk-tools==X`) and moves the tools' tested range to `>=X,<next minor`;
`verify-versions` refuses a kit whose pins lag and a tools manifest whose
range excludes the runtime next to it; `build-python` builds three wheels
and the recipe three outputs with `pin_subpackage(..., exact=True)`. One
`python-v*` tag therefore publishes three artifacts whose numbers agree.

The independent `runtime-v*` and `tools-v*` scopes, the per-distribution
publish steps, the rehearsal and the `qgis-sdk check` version diagnostic
remain TASK-57's acceptance criteria 2 to 4 and follow in the same
milestone. They are the point at which the tools may release without the
runtime; nothing before the freeze requires them, so they are not what
gates the wheels.

## Consequences

- The tree moves: `packages/qgis-sdk-runtime/src/qgis_sdk`,
  `packages/qgis-sdk-tools/src/qgis_sdk_tools`, and
  `packages/qgis-sdk-python` becomes the code-free `qgis-sdk` kit that
  still owns the shared test suite, the developer scripts and the recipe.
  Two source roots go on `PYTHONPATH`; CI installs the runtime and the
  tools editable before the kit's `dev` extra.
- The first `python-v0.5.0` release replaces the PyPI placeholders. Until
  then `pip install qgis-sdk-runtime` yields the empty `0.0.0`; the
  placeholders are yanked after the first real publish (user-side act).
- The 0.4.0 `qgis-sdk` wheel stays what it is; the 0.5.0 migration note
  (doc-12) states what console users and plugin authors install.
- The `0.x` runtime remains free to move between minors; the tools' range
  `>=X,<X+0.1` is the honest statement of what was tested, and the
  per-release re-stamp keeps it honest.
- Decision-35's versioning rule for the runtime (major iff a contract
  version bumps) begins to bind at the freeze; before it the runtime is
  `0.x` like everything else.
