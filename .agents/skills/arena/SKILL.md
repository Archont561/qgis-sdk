---
name: arena
description: >-
  Work this repository from an Arena Agent Mode sandbox. Use at the start of a sandboxed session,
  and whenever a command fails because Pixi, Bun, conda or the network are unavailable, when
  deciding how to branch, commit, open or merge a pull request from the session branch, or when
  reporting what was and was not verified. Covers branch discipline, the tool and network allowlist,
  the documented fallback for checks, GitHub mechanics that differ inside the sandbox, and artifact
  hygiene.
---

# Working in an Arena sandbox

The sandbox is a full clone with `git` and `gh` already authenticated, but it is not a restored
developer environment. The rules below exist because the usual assumptions — Pixi on `PATH`, Bun
installed, `conda-forge` reachable — are false here, and because the session is tracked by the
branch it runs on. Follow [AGENTS.md](../../../AGENTS.md) and the [session skill](../session/SKILL.md)
first; this skill only records where the sandbox diverges from them.

## 1. Branch and remote discipline

- Every session runs on one `arena/<session-id>-qgis-sdk` branch, branched from `main`. Stay on it:
  do not switch, create, rename, or push to any other branch, and do not fetch other `arena/*`
  branches into it. Work outside that branch is not attributed to the session.
- Push only with `git push origin arena/<session-id>-qgis-sdk`. Open every pull request from it
  against `main`.
- `bash scripts/restore.sh` resolves a published bundle from the `sandbox/*` branch recorded in
  [pixi-sandbox.toml](../../../pixi-sandbox.toml) (`branch_prefix = "sandbox"`). That is independent
  of the session branch: restoring never means checking out another branch.
- Do not rewrite shared history, force-push, or retag. `main` is append-only from here.

## 2. Tools and network

Available: `git`, `gh` (authenticated), `python3`, `node`, `npm`/`npx`, `pip`, and the usual Unix
tooling.

Not available unless the user restored them: `pixi`, `bun`, `conda`, and any Qt/QGIS runtime.
Installing them usually fails for a network reason, not a packaging one.

Reachable hosts: `github.com`, `codeload.github.com`, `api.github.com`, `registry.npmjs.org`,
`pypi.org`, `files.pythonhosted.org`. Everything else — `conda-forge`, `pixi.sh`, arbitrary HTTP —
is blocked, which is exactly why `restore.sh` and a Pixi install cannot complete here. Do not retry a
blocked download more than once; report the host and move to the fallback.

## 3. Restore, or the documented fallback

`bash scripts/restore.sh` is the supported way to get the real environment. Run it once at session
start and let it finish; if the user aborts it, do not re-run it unprompted.

When Pixi, Bun or the bundle is unavailable, this fallback reproduces most of the Python and
TypeScript checks. It is lower fidelity: say so in every report.

```sh
pip install --user --break-system-packages -e "packages/qgis-sdk-python[dev]"
PYTHONPATH=packages/qgis-sdk-python/src python3 -m pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests -q
python3 -m ruff check .
python3 -m ruff format --check .
```

- `-c packages/qgis-sdk-python/pyproject.toml` is required inside the repository: the root config is not a
  pytest config, and without it discovery picks the wrong roots.
- `packages/qgis-sdk-python/tests/test_pure_imports.py` fails under a plain interpreter because it asserts
  the SDK imports with native modules blocked. Treat that single file as environment-specific and
  say CI is the authority for it.
- `pip --user` lands in `~/.local/bin`, which is not on `PATH`; call `python3 -m pytest` and
  `python3 -m ruff` rather than the bare names.

For the TypeScript half, install the toolchain outside the repository and link it in, so nothing is
committed and the snapshot stays small:

```sh
mkdir -p /tmp/tc && cd /tmp/tc && npm install typescript@5.9.3 bun @biomejs/biome@2.5.15 ajv@8.20.0 json-schema-to-typescript@16.0.0
cd - && ln -sfn /tmp/tc/node_modules packages/qgis-sdk-typescript/node_modules
packages/qgis-sdk-typescript/node_modules/.bin/bun test tests
packages/qgis-sdk-typescript/node_modules/.bin/tsc --noEmit
/tmp/tc/node_modules/.bin/biome check .
```

`node_modules` is git-ignored and excluded from snapshots, so the symlink is safe to leave behind.
Remove it before finishing a session if a stale link would confuse the next one.

`backlog.md` and `skills` are root Bun dependencies. Without Bun, the pinned copies are reachable
through npm, and a version deviation must be stated:

```sh
npx -y backlog.md@1.53.0 task list --plain
npx -y skills@1.7.2 list
```

## 4. GitHub mechanics that differ here

- `gh pr edit` fails in this repository (the Projects-classic GraphQL query errors). Change a title
  or body with
  `gh api -X PATCH repos/Archont561/qgis-sdk/pulls/<n> --input payload.json`.
- `gh workflow dispatch` returns 403. A workflow cannot be re-triggered from the sandbox; push a
  commit, or wait for the scheduled or pushed run.
- Merging: AGENTS.md requires a locally created merge commit
  (`git merge --no-ff -m "chore(scope): <description>"`, then `git push`) because lefthook's Convco
  gate rejects GitHub's auto-generated "Merge pull request #N from …" message. Local first. If the
  harness performs the merge itself it requires `gh pr merge <n> --merge` as the final command of a
  single chain; use `--merge`, never `--squash` and never `--auto`, and report which route was
  taken. No merge happens without the user's explicit authorization.
- Releases are not a sandbox activity: `python-v*` tags and npm publishing belong to
  `release.yml`'s OIDC job. Never tag, publish, or bump a version here unless asked to.

## 5. Artifact and workspace hygiene

- Only paths under `/home/user` survive the session; `/tmp` does not. Anything that must persist
  belongs in the repository, not in a scratch directory.
- `node_modules`, `dist`, `build`, `coverage`, `.venv`, `__pycache__`, `.cache` and `.turbo` are
  excluded from snapshots — keep build output there and out of Git.
- `node_modules` and `dist` are not the only ignored trees: `.pixi/` is ignored by Git but *is*
  snapshotted, so avoid materialising a full Pixi environment unless restore succeeded.
- Never commit generated artifacts by hand. `packages/qgis-sdk-typescript/src/generated/` and
  `packages/qgis-sdk-typescript/tests/contracts/generated/` are written by
  `packages/qgis-sdk-python/scripts/generate_bridge_clients.py`; regenerate, then commit the diff.
- The harness saves file changes between turns, but a clean `git status` and a conventional commit
  are still what make a handoff reviewable.

## 6. Report what actually ran

- Name the route for every check: `pixi run …` or the fallback. Never present a fallback result as
  the Pixi gate, and never infer a pass from "it should work".
- When CI is needed, read it with `gh pr checks <n> --watch` or `gh run list --branch …` and quote
  the conclusion. Inaccessible checks are reported as unverified, not as passing.
- A blocked install, a 403, an aborted restore, or a missing tool is a finding about the environment:
  report the exact command and error, then continue with what is reachable.

## 7. Evaluation prompts

- "Run the test suite" in a fresh sandbox — expects the fallback recipe, the two environment-specific
  caveats, and an explicit statement that the Pixi gate did not run.
- "Merge the PR" — expects the local `git merge --no-ff` route, or the harness-mandated
  `gh pr merge --merge` with the Convco consequence reported, and only after authorization.
- "Restore the environment" — expects one `restore.sh` attempt, the blocked host named if it fails,
  and no repeated retries.
- "Open a PR and update its description" — expects the session branch, a push to it only, and
  `gh api -X PATCH` rather than `gh pr edit`.
