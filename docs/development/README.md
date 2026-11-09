# Development

Contribution, testing and release workflows. The workspace guide in
`apps/docs/guides/doc-14` is the reference; this page is the way in.

## Set up

```sh
bash scripts/restore.sh            # locked Pixi environments, offline-capable
pixi run -e bun bun run test       # Python and TypeScript tests
pixi run -e bun bun run coverage   # the 90% gates CI uses
```

- [Quick start](https://archont561.github.io/qgis-sdk/contributing/workspace/quick-start/)
- [Development environments](https://archont561.github.io/qgis-sdk/contributing/workspace/development-environments/) - what each Pixi environment carries.
- [Test, build and the Pixi tasks](https://archont561.github.io/qgis-sdk/contributing/workspace/test-build-and-the-pixi-tasks/)
- [Repository layout](https://archont561.github.io/qgis-sdk/contributing/workspace/repository-layout/)

## Change a package

- [Test layers](https://archont561.github.io/qgis-sdk/contributing/workspace/test-layers/) - which layer a test belongs to, and the marker that selects it.
- [Python package development](https://archont561.github.io/qgis-sdk/contributing/workspace/python-package-development/)
- [Contract generation](https://archont561.github.io/qgis-sdk/contributing/workspace/contract-generation-checked-example/) - regenerating the schema and the typed clients, and the check that they are current.
- [Contributing](https://archont561.github.io/qgis-sdk/contributing/workspace/contributing/) - the rules a change is reviewed against.

## Change the documentation

- [Documentation site](https://archont561.github.io/qgis-sdk/contributing/workspace/documentation-site/) - the Fumadocs site, its generator, the exports and the link check.
- [The documentation policy](../README.md) - what has to be true before a change is considered documented, and the checks that enforce it.
- `bun run readme` - regenerate the root landing page from `scripts/readme/template.ejs`.

## Release

- [Workspace, harnesses and evidence](https://archont561.github.io/qgis-sdk/contributing/workspace/) - release scopes, the harnesses, and what has been proven on a real QGIS host.
- `backlog/tasks/` - the task records, including the release tasks.

## Sources

- `AGENTS.md` - the working agreement for this repository.
- `apps/docs/guides/doc-14 - Workspace-development-qualification-harnesses-and-evidence.md` - the full workspace guide.
- `.github/workflows/` - what CI runs, in the order it runs it.
