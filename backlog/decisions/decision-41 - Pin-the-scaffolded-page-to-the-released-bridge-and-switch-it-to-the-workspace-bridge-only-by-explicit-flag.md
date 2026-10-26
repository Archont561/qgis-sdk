---
id: decision-41
title: Pin the scaffolded page to the released bridge and switch it to the workspace bridge only by explicit flag
date: '2026-10-26 13:00'
status: accepted
---
## Context

`qgis-sdk new --web` writes a `web/package.json` whose `@archont561/qgis-sdk`
entry was a literal in `qgis_sdk_tools/scaffold/web.py` (`SDK_NPM_VERSION`),
edited by hand when someone remembered. Nothing moved it when the bridge was
released, and nothing checked it: the scaffold could pin a bridge older than
the one the tools were qualified with, or a version that did not exist yet.

The same template serves two audiences with opposite needs. A plugin author
outside this repository wants a page that installs from the registry and
keeps working - an exact pin of a published release, as every other
dependency of the generated page is pinned (decision-18). Inside this
repository - the reference plugin `examples/simple` and the opt-in harnesses
that scaffold into a temporary directory - the page must run on the bridge of
the *checkout*, or the harnesses prove nothing about the code under review
and the example cannot use a bridge change until it is published.

Two mechanical facts shaped the in-repository half. Bun refuses
`file:<directory>` for `packages/qgis-sdk-typescript`: it treats a folder
dependency like a workspace member and tries to install the folder's own
`workspace:*` tooling, which does not resolve outside the workspace; and
Bun's `link:` protocol names a `bun link` registration, not a path. What
every manager (bun, npm, pnpm) accepts identically is `workspace:*` inside a
workspace and `file:<tarball>` anywhere.

## Decision

1. **Users get an exact pin that the release pipeline owns.** `SDK_NPM_VERSION`
   stays an exact version. `release.py stamp --scope typescript` rewrites it
   together with the bridge's `package.json` and the alias pin, and
   `verify-versions` reports it as the `scaffold pin`; a `tests/scripts` test
   fails when the checked-in pin disagrees with the bridge manifest. So a
   `qgis-sdk-tools` release offers the newest bridge it was qualified beside,
   never a registry lookup at scaffold time and never a caret range.
2. **The switch is explicit.** `qgis-sdk new --sdk-dependency SPEC`
   (`ScaffoldOptions.resolve(sdk_dependency=)`, `WebOptions.sdk_dependency`)
   replaces that one value with any npm spec. It is refused without `--web`,
   like `--placement`, and refused when blank or containing whitespace. The
   scaffold does not detect that it runs inside the SDK repository: a path
   guess would make the generated page depend on where the command happened
   to run, and the two in-repository callers already know what they want.
3. **The example is a workspace member.** The root `package.json` lists
   `examples/*/web` among its workspaces; `examples/simple/web/package.json`
   depends on `@archont561/qgis-sdk` as `workspace:*` and has no lockfile of
   its own. Turbo's `test` task depends on `^build`, so the example's Vitest
   suite runs on a freshly built `packages/qgis-sdk-typescript`
   (`pixi run -e bun test-reference-web`, a CI step). A pure test holds the
   example's `web/package.json` equal to the scaffold's for that spec.
4. **The harnesses get a tarball.** The session fixture `workspace_bridge`
   builds the bridge and packs it with `bun pm pack`; `QGIS_SDK_REFERENCE=1`
   and `QGIS_SDK_SCAFFOLD_WEB=1` pass `file:<tarball>` through the same flag.
   A tarball is what a release ships, so a page that passes on it passes on
   the published package, with every manager. The reference harness copies
   the example over the scaffold without `web/package.json`.

## Consequences

- Every bridge release moves the scaffold pin in the same stamp commit; the
  pin can no longer lag or lead. `ts-v0.4.0` (TASK-60) is the first stamp
  that does so.
- Pages generated for users keep installing from the registry with an exact,
  qualified version. *(Status review below: the templates moved to the root
  barrel and `QgisSdk` with the package source; the pin follows at the stamp.)*
- The root `bun.lock` carries the example's Vite, Vitest and happy-dom
  pins; `bun install --frozen-lockfile` covers them. Running the example's
  page now starts with `bun install` at the repository root.
- A fourth kind of in-repository consumer (a second example, a docs site
  page) chooses between `workspace:*` and a packed tarball by whether it
  lives inside the workspace; neither needs new scaffold code.

## Status review (2026-10-26): templates follow the source, the pin follows the stamp

The consequence above predicted that the templates would keep importing
`@archont561/qgis-sdk/bridge` until the pin named a release with the root
barrel. TASK-66 took the other reading, and this decision's mechanics are
what make it safe: the templates are qualified against the checkout's bridge
through the `file:<tarball>` and `workspace:*` paths of point 4, the pin is
owned by `release.py stamp --scope typescript` (point 1), and the TASK-60 gate
stamps tools `0.6.0` and bridge `0.4.0` in one commit. So the templates now
write the three-statement page of decision-44 while `SDK_NPM_VERSION` still
says `0.3.0`; a `qgis-sdk new --web` from an unreleased `main` is a
pre-release page against a pre-release pin, like every other artifact on
`main` between gates, and a released tools version never scaffolds against a
bridge it was not qualified beside. Points 1-4 and the consequences other than
the one marked stand.
