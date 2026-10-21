---
id: doc-8
title: GitHub Actions outage window and the no-CI evidence protocol
type: other
created_date: '2026-10-21 21:56'
updated_date: '2026-10-21 21:56'
---
# GitHub Actions outage window and the no-CI evidence protocol

Recorded 2026-10-21. GitHub Actions cannot start jobs on this account, and it will not until
billing or the spending limit is handled, which the user has scheduled for **next month
(November 2026)**. This document is the standing constraint for that window: what is blocked,
what still counts as evidence, and what must be backfilled once runners return.

## Symptom, and how to re-check it in thirty seconds

Every job on every branch - PR jobs, `main`'s scheduled `publish-sandbox` run, and jobs of
docs-only pull requests - fails after 2-4 seconds with **zero steps executed** and this
annotation:

> The job was not started because recent account payments have failed or your spending limit
> needs to be increased. Please check the 'Billing & plans' section in your settings

`gh run view --log-failed` is no help here (the log host is unreachable, or the run is still
reported as in progress). What works:

```sh
SHA=$(gh pr view <n> --json headRefOid --jq .headRefOid)
for id in $(gh api "repos/Archont561/qgis-sdk/commits/$SHA/check-runs" \
    --jq '.check_runs[] | select(.conclusion=="failure") | .id' | head -2); do
  gh api "repos/Archont561/qgis-sdk/check-runs/$id/annotations" --jq '.[].message'
done
```

`main` failing identically is the proof that the cause is account state rather than the diff.
Do not modify the repo to chase it, and do not re-run hoping for a different runner.

## Scope of the blockage

All five workflows are Actions-only: `ci.yml` (push/PR), `relock.yml` (PR plus the relock-bot
dispatch), `publish-sandbox.yml` (push to `main` plus the weekly `17 4 * * 1` cron),
`autorelease.yml` (push to `main` plus dispatch) and `release.yml` (`v*` tag pushes).

`release.yml` is the **only publisher**: PyPI and npm publishing is OIDC trusted publishing
bound to that file and the `pypi` / `npm` environments, so during the window there is no way to
publish at all - this is not merely an evidence gap. Hand-publishing with local registry
credentials is refused on purpose: TASK-35 fixed "no long-lived registry tokens or secrets",
and the first genuine upload is meant to be the first clean tag.

Acceptance criteria that cannot be checked in this window:

| Task | Blocked AC | What is missing |
| :-- | :-- | :-- |
| TASK-27, 28, 29, 30, 31, 32 | each `#4` | CI-produced artifacts plus checks and an explicit publishing approval |
| TASK-27 | `#1` partly | it requires unresolved targets/spikes to close, and TASK-13 `#1` and TASK-33 cannot close here |
| TASK-36 | `#1`, `#4` | the extracted repo's pipeline and "one full autorelease-then-release cycle runs green" run on the same account, so extraction does not escape the outage |
| TASK-17 | `#3` | `CI drift checks protect generated-file ownership`; the local generator proves no drift per change, which is not a gate |
| TASK-9 | `#1`, `#3` | release checks on supported environments, and the lockfile check that CI/release relies on |
| TASK-33 | `#1`, `#2`, `#3` | a clean Windows install and a Desktop session with a display; `ci.yml`'s `cross-platform (${{ matrix.os }})` job was the other source |
| TASK-22 | `#3` | clean-profile Windows evidence |
| TASK-24 | `#3` | `real Desktop startup/unload evidence` - a headless run is not a Desktop session and must not be substituted |
| TASK-13 | `#1` | candidate target runtimes beyond Linux/CPython 3.14.8 |

Deliberately **not** blocked: TASK-33 `#4` ("publish evidence and blockers for any target that
remains unavailable") is precisely what this window can produce honestly. And TASK-1, 3, 4, 5,
6, 7, 8, 14, 15, 16, 18, 19, 20, 21, 25, 26 remain fully workable, including their QGIS paths,
against the real QGIS 4.2.3 available headless in the `default` environment.

## What is not lost

`autorelease.yml` derives its plan from tags and commit history, not from the pushes it missed
(Actions does not replay skipped events), and `pixi run release-plan` on 2026-10-21 returned
`action=skip tag=v0.1.0 reason=no stable tag exists yet`. So the first push to `main` after
the fix will plan the whole window at once, and the first-stable guard keeps 0.1.0 a
deliberate dispatch. No release is silently skipped, and no version decision expires.

## Evidence standard for the window

1. Land on the local gate set and print freshness next to the counts: `bun run test` has to
   report `Cached: 0 cached`, because a Turbo replay is not evidence. Then `bun run coverage`
   (the Python and bridge 100 % gates), `pixi run lint-python`, `pixi run format-python-check`,
   `bunx biome check .`, the bridge `typecheck` and `build`, the opt-in real-QGIS smokes via
   `QGIS_SDK_HEADLESS_LIFECYCLE=1 QGIS_SDK_HEADLESS_SMOKE=1 QGIS_SDK_QT_SCHEDULER=1`,
   `bun run sdk:generate` followed by `git status --porcelain` for contract drift, and
   `pixi run release-build-python` plus `release-verify-python` whenever a packaging boundary moved.
2. Never check an AC whose wording names CI, a runner, a registry, a display or a platform.
   Leave it unchecked and add a `blocked-by-actions` comment pointing here - all thirteen
   tasks in the table carry one as of 2026-10-21 - so the backfill list is mechanical instead
   of archaeological.
3. Say the CI gap out loud in every PR body the way #21, #23 and #24 did, and never use a
   breaking-change marker to describe something the registries never shipped.

## Day one after billing is restored

1. Prove runners exist with one cheap dispatch or docs push before trusting any result.
2. `pixi lock --check`, then `bash scripts/restore.sh` followed by `pixi run -e bun install-js`:
   the weekly `publish-sandbox` upgrade cron has been dark for a month, so the sandbox bundle
   is stale by design. Expect the nine known site-packages `RECORD` integrity complaints
   (certifi, idna, jsonschema, packaging, pip, requests, urllib3, mako, pytest-bdd): the
   restore exits 1 on them, they predate this window, and `scripts/` tracks only `restore.sh` -
   there is no separate verify-env script to run.
3. Expect runner-image noise. Jobs already carried "The `ubuntu-latest` label will migrate to
   Ubuntu 26 beginning October 19, 2026", and `ci.yml` pins `actions/checkout@v7`,
   `prefix-dev/setup-pixi@v0.11.2` and `codecov/codecov-action@v7` by tag (the release
   workflows are SHA-pinned). Compare against a `main` run before editing code.
4. Backfill the deferred ACs in the table, then resume the release chores in order: TASK-27,
   the deliberate 0.1.0 dispatch, TASK-28 onward.
5. Optional and unverified: a self-hosted runner on real Windows/macOS hardware could satisfy
   TASK-33 `#1`/`#2` and TASK-13 `#1` at zero Actions cost. Whether a failed payment disables
   Actions for the account outright or only GitHub-hosted minutes has not been tested here;
   try one trivial workflow before planning around it.
