---
id: decision-35
title: Split the Python SDK into a runtime, a tools package and a meta kit behind one contract
date: '2026-10-25 15:10'
status: accepted
---
> **Amended:** [decision-67](decision-67%20-%20Retire-the-optional-Pydantic-controlled-deployment-adapter.md) retires the optional Pydantic adapter and `controlled-deployment` extras for a future Python minor release. Historical descriptions below reflect the original decision.

## Context

`qgis-sdk` is one wheel holding two things with opposite lifecycles. The code
a plugin imports inside QGIS (`models`, `declarations`, `core`, `services`,
`resources`, the bridge host side, the adapters) must be stable, stdlib-only
and vendorable plugin-private (decision-3). The code a developer runs before
the plugin exists (`scaffold`, `check`, `devtools`, the Typer CLI, the pytest
plugin, the bridge generator) may churn freely and needs dependencies a user's
QGIS does not have. Keeping them in one distribution has three costs:

- **Mismatches are invisible.** Which part of "the SDK" a plugin depends on,
  and which part a release changed, is not expressible in a version number.
  decision-25 already separated the TypeScript bridge from Python for the
  same reason: the real coupling is the contract, not a release train.
- **Console use has no home.** A user who wants the typed services from the
  QGIS Python console would have to install the whole kit - Typer included -
  into the QGIS interpreter, next to the plugin-private copies decision-3
  mandates, with `import qgis_sdk` resolving to whichever is first on
  `sys.path`.
- **The ZIP rule is a list, not a boundary.** `qgis-sdk build` (TASK-8) must
  ship "the runtime modules" and exclude "dev tooling"; today that is an
  exclusion list over one tree rather than a package boundary.

The user confirmed the shape on 2026-10-25 and reserved the registry names:
`qgis-sdk-runtime` and `qgis-sdk-tools` exist on PyPI at a placeholder
`0.0.0` with trusted publishing bound to `release.yml` / environment `pypi`,
and the prefix.dev channel accepts `qgis-sdk*`.

## Decision

Three Python distributions and the TypeScript package, around one contract.

| Distribution | Import name | Who imports it, when | May depend on |
| :-- | :-- | :-- | :-- |
| `qgis-sdk-runtime` | `qgis_sdk` | the plugin inside QGIS; console scripts | stdlib only; QGIS/Qt are host-provided, never declared |
| `qgis-sdk-tools` | `qgis_sdk_tools` | the developer's shell and CI | the runtime (tested range), Typer, pytest, anything |
| `qgis-sdk` | none (meta) | `pip install qgis-sdk` | runtime + tools at same-release pins; extras for options |
| `@archont561/qgis-sdk` | - | the web page | the contract versions only (decision-25) |

**The boundary test:** a module needed by a built ZIP running in a user's
QGIS is runtime; a module that needs anything not in a user's QGIS (Typer,
pytest, a package manager, a source tree) is tools. Nothing is in both.

**Runtime** (`src/qgis_sdk`): `models`, `declarations`, `algorithms`, `jobs`,
`providers`, `ui`, `resources`, `reference`, `core`, `services`, `network`,
`bridge` minus the generator, `adapters` (including `pydantic*` behind its
extra), and `qgis_sdk.testing` - the fakes implement the runtime's protocols
and version with them; `build` excludes them from the ZIP. The contract
constants (`PLUGIN_DESCRIPTION_SCHEMA_VERSION`, `BRIDGE_PROTOCOL_VERSION`,
`HOST_SCHEMA_VERSION`) live here and are the only coupling tools and the
TypeScript package may rely on. Environment variable names a generated
plugin reads (`QGIS_SDK_DEV_SERVER`, `QGIS_SDK_TEST_TARGET`) are runtime
constants that tools imports, not strings both sides happen to know.

**Tools** (`src/qgis_sdk_tools`): `__main__`, `cli`, `scaffold`, `check`,
`devtools`, `pytest_plugin`, the bridge generator, `FakeCliRuntime`, and the
`qgis-sdk` console script. Tools errors subclass the runtime's
`QgisSdkError`; the runtime never imports tools - the pure-layer test
enforces both directions. Headless-QGIS knowledge (profiles, `--code`
probes, Chromium flags) is tools knowledge.

**Meta** (`qgis-sdk`): no code. Its base dependencies are the runtime and
tools - the name keeps meaning "the developer kit" - with extras for options
(`controlled-deployment`, later the QGIS-free preview). Console users install
`qgis-sdk-runtime` by name; plugins pip-install nothing, `build` vendors the
runtime under an import-renamed path so two plugins with two runtime
versions coexist (decision-3's two-plugin test). This amends decision-3's
"no shared runtime for v1": a shared runtime exists *for console use only*
and is never what a plugin imports.

**Versioning.** The runtime's major bumps if and only if a contract version
bumps; its minor for additive protocol surface. Tools versions freely - its
number tells a developer about their workflow, not about plugin
compatibility - and declares the runtime range it tested. The meta tracks
tools. Scopes `runtime-v*` and `tools-v*` join `python-v*` (the meta) and
`ts-v*` in `release.py`; each distribution has its own publish step so a tag
publishes exactly one artifact and a failure is attributable.

**Sequencing.** Step 1, now: split the *tree and the rules* inside the one
`qgis-sdk` wheel (`src/qgis_sdk_tools` next to `src/qgis_sdk`, the layer
test extended, the console script moved, the scaffold's `addopts` and
imports repointed). It is cheap today because `pytest_plugin`, `devtools`
and the scaffold's plugin reference are unreleased; `qgis_sdk.scaffold` and
`qgis_sdk.check` as Python APIs move with a 0.x migration note. Step 2, at
the contract freeze: cut the three distributions, the release scopes, the
publish steps and the multi-output recipe. The freeze is a separate,
explicit decision: it is the point at which `PluginContext`, the service
protocols, the description schema and the bridge protocol stop moving
between minors.

## Consequences

- `qgis-sdk build` ships the runtime tree and nothing else; the exclusion
  list becomes a package name.
- Step 1 breaks `from qgis_sdk.scaffold import ...` / `qgis_sdk.check` for
  anyone scripting those (pre-1.0, documented); CLI command names, generated
  project layout and the runtime API are unchanged. Projects generated
  before step 1 that used the unreleased `-p qgis_sdk.pytest_plugin` must
  repoint it; none were released.
- Until step 2, one wheel still carries both trees, so the dependency split
  is enforced by the layer test, not by pip. The tools tree may import
  Typer; the runtime tree may not import anything outside the stdlib.
- The tools-to-runtime version matrix is tools' testing burden. Scaffold
  templates state the runtime range they target.
- A fourth piece - the QGIS-free preview host (decision-8's "fake preview")
  - would be a tools extra over the runtime's fakes, not a new package.

## Status review (2026-10-26): vendoring stays the only mechanism through 0.x

Asked whether pip inside QGIS's bundled Python could hold several runtime
versions so plugins could skip vendoring: it cannot - one importable name per
environment, multi-version eggs are gone, `metadata.txt` names only plugin
dependencies, and OSGeo4W / the macOS bundle / PEP 668 distros make any
install step a support burden. Version-suffixed import names were rejected as
worse than vendoring on every axis but disk. The post-1.0 shape, recorded here
and not scheduled: the generated `classFactory` tries a shared `qgis_sdk`
that satisfies the plugin's declared requirement (decision-43 amendment) and
falls back to the vendored copy otherwise. It becomes worth building only once
the runtime carries a backward-compatibility promise (decision-25's stability
clause). The vendored set already excludes `qgis_sdk.testing` and
`__pycache__` (`bundle/vendor.py`); nothing further to prune today.

