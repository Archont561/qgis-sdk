---
id: decision-50
title: Declare third-party Python packages as externals with a startup probe and vendor only pure-Python ones
date: '2026-10-26'
status: accepted
---
## Context

A plugin author who imports `pandas` in an algorithm is refused by `build`
today (`DEP001`: the ZIP cannot carry it) and has two exits: declare the
import root under `[tool.qgis-sdk.build] external` ("every QGIS I target ships
it"), after which a QGIS that lacks it fails with a traceback at load; or
vendor the package by hand, which works for small pure-Python libraries and
not at all for compiled ones. The SDK deliberately never runs `pip install`
on the user's machine (PEP 668 distros refuse it, OSGeo4W needs elevation,
and it mutates the user's QGIS Python; decision-35, 43). The gap is that
neither exit is honest to the end user.

## Decision

1. **Externals are declared with a requirement and probed at startup.**
   `[tool.qgis-sdk.build] external` accepts tables as well as bare roots:
   `{ import = "pandas", requirement = "pandas>=2", reason = "..." }`.
   `build` (TASK-64's generated `classFactory`) emits a probe that imports
   each external before constructing the plugin; on failure it shows one
   message-bar error naming the package and the install hint for the
   detected host (OSGeo4W shell `pip install`, the QGIS.app `pip3`, the
   distro package name when declared) and leaves the plugin unloaded
   cleanly instead of half-initialised. The declared externals are
   rendered into the generated `metadata.txt` description so the plugin
   manager shows them before installation.
2. **Pure-Python packages can be vendored by the build.**
   `[tool.qgis-sdk.build] vendor = ["<distribution>", ...]`: `build` copies
   the installed package from the author's environment under
   `<plugin>/_vendor/` with the same import rewrite the runtime receives,
   records name and version in the ZIP notice and the license file in
   `_vendor/LICENSES/`. A distribution with any compiled extension
   (`.so`/`.pyd`/`.dylib`) is refused with `DEP003` ("cannot vendor a
   compiled package; declare it external"). A vendored distribution's own
   dependencies must be vendored or external too (`DEP004` names the
   missing one).
3. **`check` sorts every import into a bucket** - stdlib, host, runtime,
   plugin, vendored, external, unknown - and reports unknown ones as
   `DEP001` at check time, not first at build time, with the two exits in
   the remediation.
4. **Compiled packages stay external.** doc-12 says plainly that `pandas`,
   `scipy`, `shapely` and similar are externals with a probe, never
   vendored, and that an author who needs them in a QGIS that lacks them
   has to tell their users how to install them.

## Consequences

- An end user sees "this plugin needs pandas; install it with ..." in the
  message bar instead of a traceback; a developer learns the bucket of
  each import at `check`.
- `build` gains a vendoring path with a compiled-code refusal; the ZIP
  grows by the vendored pure-Python packages only.
- The SDK still never installs anything on a user's machine.
- Scheduled as TASK-77 in m-6, after TASK-64 (the generated `classFactory`
  is where the probe lives).
