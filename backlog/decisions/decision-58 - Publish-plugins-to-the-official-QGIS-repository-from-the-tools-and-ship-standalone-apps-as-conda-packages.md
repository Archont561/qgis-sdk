---
id: decision-58
title: Publish plugins to the official QGIS repository from the tools, and ship standalone apps as conda packages
date: '2026-10-26'
status: accepted
---
## Context

`build` produces a plugin ZIP and stops. Getting it to users - the official
QGIS plugin repository, a private repository, a standalone app on a
colleague's machine, a server plugin on a host - is undocumented and
unmechanised. The official repository has its own rules (metadata keys,
`experimental`, version monotonicity, changelog, license) that `check`
could enforce before an upload is refused.

## Decision

1. **`qgis-sdk publish`** uploads the built ZIP to the official repository
   (`plugins.qgis.org` XML-RPC) or to a private repository directory /
   URL with a generated `plugins.xml`. Credentials come from the
   environment or a keyring the user controls; the tools never store or
   prompt for them (decision-35 spirit). `--dry-run` validates only.
2. **`PUB00x` check rules** mirror the repository's acceptance rules:
   required metadata keys and lengths, `experimental` vs. version,
   version greater than the last published (queried, if reachable),
   changelog present and derived from the release notes, license file,
   icon size, no compiled files unless declared external, ZIP root layout.
   `build` runs them; `publish` refuses on any finding.
3. **Server plugins** are the same ZIP installed into `QGIS_PLUGINPATH`;
   a guide ships a Docker example (`qgis/qgis-server` image + the plugin)
   and the `dev --host server` loop; no further mechanism.
4. **Standalone apps** ship as a conda package built by `build --target
   app` through a generated `rattler-build` recipe (QGIS itself comes from
   conda-forge, so this is the one channel that can carry the dependency),
   plus the plain wheel for environments that already have QGIS. Native
   installers (MSI, DMG, AppImage) are out of scope by decision until a
   user asks; the recipe is the input they would wrap.
5. **Release notes are the changelog source** for all three: `release.py
   plan` already writes them; `build` renders the plugin's own changelog
   from its project's Conventional Commits the same way.

## Consequences

- One more network-touching command in the tools, with the same
  no-credential-storage rule as PyPI/npm trusted publishing.
- Tasks: TASK-100 (publish command, PUB rules, private repository) and
  TASK-101 (app conda recipe, server guide) in m-11.
