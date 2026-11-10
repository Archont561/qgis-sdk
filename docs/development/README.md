# Development

Contribution, testing and release workflows. The workspace guide in
`apps/docs/guides/doc-14` is the reference; this page is the way in.

## Set up

```sh
bash scripts/restore.sh            # locked Pixi environments, offline-capable
pixi run automation list            # every repository task and what it does
pixi run automation check           # Ruff, format, clean code, Alint and actionlint
pixi run automation test_python     # the QGIS-free suite of the kit
pixi run -e bun bun run test       # Python and TypeScript tests
pixi run -e bun bun run coverage   # the 90% gates CI uses
```

- [Quick start](https://archont561.github.io/qgis-sdk/contributing/workspace/quick-start/)
- [Development environments](https://archont561.github.io/qgis-sdk/contributing/workspace/development-environments/) - what each Pixi environment carries.
- [Test, build and the Pixi tasks](https://archont561.github.io/qgis-sdk/contributing/workspace/test-build-and-the-pixi-tasks/)
- [Repository layout](https://archont561.github.io/qgis-sdk/contributing/workspace/repository-layout/)

## Python versions

The three distributions promise `requires-python = ">=3.11"`, and the Pixi
environments only ever run the newest interpreter, so the floor is checked
separately:

```sh
pip install tox==4.67.13      # tox is not a Pixi dependency
tox -e py311                  # one version, in its own venv
tox                           # every version installed here
```

`tox.ini` names one environment per version from the floor to the pinned
interpreter and installs the runtime and the tools from their source trees. CI
runs one job per version in `.github/workflows/compat.yml`; `tests/scripts/test_python_versions.py`
keeps the manifests, the envlist and the matrix from drifting apart.

## Clean code

Rude and its `rude-clean-code` plugin measure every Python definition in the
repository: how long functions and classes are, how many parameters, returns and
locals they take, how deep they nest, how long their boolean chains and how many
branches they own (CC101-CC303). The thresholds are `[tool.rude]` in the root
`pyproject.toml`; the rules report at `WARNING` severity, so Rude exits 0
whatever it finds and the gate is the comparison, not the exit status.

```sh
pixi run automation clean_code               # the tree against the budget
pixi run automation clean_code --rebaseline  # rewrite the budget from the tree
```

`clean_code_budget.json` is the committed count per file and rule, and the check
fails on any movement: a file that grows a violation, a new file that arrives
with one, and a violation fixed without the budget being lowered in the same
change. New code starts clean. Lowering the budget is part of the fix, which is
what makes the number a ratchet instead of a ceiling.

The full account of the layer is in the workspace guide
(`apps/docs/guides/doc-14`); Ruff keeps its own `F`/`E`/`W` and `C901` sets in
`ruff.toml`, so the two linters do not report the same finding twice.

## Change a package

- [Test layers](https://archont561.github.io/qgis-sdk/contributing/workspace/test-layers/) - which layer a test belongs to, and the marker that selects it.
- [Python package development](https://archont561.github.io/qgis-sdk/contributing/workspace/python-package-development/)
- [Contract generation](https://archont561.github.io/qgis-sdk/contributing/workspace/contract-generation-checked-example/) - regenerating the schema and the typed clients, and the check that they are current.
- [Contributing](https://archont561.github.io/qgis-sdk/contributing/workspace/contributing/) - the rules a change is reviewed against.

## Change the documentation

- [Documentation site](https://archont561.github.io/qgis-sdk/contributing/workspace/documentation-site/) - the Fumadocs site, its generator, the exports and the link check.
- [The documentation policy](../README.md) - what has to be true before a change is considered documented, and the checks that enforce it.
- `bun run readme` - regenerate the root landing page from `scripts/readme/template.ejs`.
- `bun run agents` - regenerate the marked regions of `AGENTS.md` with `@eugeniughelbur/agents-md`; `bun run agents:check` is what CI runs.

## Release

- [Workspace, harnesses and evidence](https://archont561.github.io/qgis-sdk/contributing/workspace/) - release scopes, the harnesses, and what has been proven on a real QGIS host.
- `backlog/tasks/` - the task records, including the release tasks.

## Sources

- `AGENTS.md` - the working agreement for this repository.
- `apps/docs/guides/doc-14 - Workspace-development-qualification-harnesses-and-evidence.md` - the full workspace guide.
- `.github/workflows/` - what CI runs, in the order it runs it.
