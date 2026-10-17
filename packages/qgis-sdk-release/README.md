# qgis-sdk-release

Release planning and publishing CLI for the QGIS SDK workspace (TASK-35).

The tool encapsulates everything `autorelease.yml` and `release.yml` need:

- `plan` — next SemVer + changelog from conventional commits per `.versionrc`,
  with the policy that the push-to-main trigger never creates a tag while no
  *stable* tag exists (bootstrapping and the first stable release are
  deliberate `workflow_dispatch` acts; prerelease suffixes keep iterating the
  rc train without arming registry publishes).
- `classify` — whether a tag is a clean release or a prerelease.
- `tag` — annotated tag creation, optionally pushed.
- `stamp` — write the release version into `packages/qgis-sdk/pyproject.toml`
  (PEP 440 form) and `packages/qgis-sdk-bridge/package.json` (SemVer form),
  working tree only; committed manifests never move during planning.
- `build-python` / `verify-python` — wheel build via `python -m build` plus
  `twine check`.
- `checksums` — `sha256sum -c` compatible `SHA256SUMS`.
- `github-release` — create the GitHub Release and upload assets over REST.

Everything runs through Pixi tasks declared in the root `pixi.toml`
(`release-plan`, `release-tag`, `release-stamp`, …) from the repository root:

```sh
pixi run -e build release-plan --trigger dispatch --suffix rc.1 --json
```

Stdlib-only by design, so the release path adds no locked dependencies.
Extraction into a standalone checksum-pinned repository (the pixi-sandbox
distribution model) is tracked as TASK-36.
