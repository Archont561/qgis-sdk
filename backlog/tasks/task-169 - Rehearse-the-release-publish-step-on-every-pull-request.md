---
id: TASK-169
title: Rehearse the release publish step on every pull request
status: Done
assignee: []
created_date: '2026-11-13 13:10'
updated_date: '2026-11-13 13:40'
labels: []
dependencies: []
ordinal: 169000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`python-v0.11.0` reached PyPI and then failed its own last step: the shell that hashes the artifacts and attaches them to the GitHub Release had been broken since the automation moved onto `doit` (TASK-35), and nothing ran it in between. Pull requests exercise every gate except this one, so a release is the first execution of `release.yml`'s publish step - which makes a release the worst possible place to discover it is wrong (PR #222 repaired the three defects it exposed).

The step also had no dry run: `github-release` calls the API the moment it is given a tag, so there was nothing a pull request could execute. This task moves the step into `automation/` as one command with a `--dry-run`, points `release.yml` at it, and rehearses it on every pull request against a fabricated artifact tree.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One command owns the step: `automation -- release_publish` resolves the artifact globs, writes `SHA256SUMS` and uploads the release, and `release.yml` calls it with no shell loop, no `--paths` and no glob expansion of its own.
- [x] #2 `release_publish --dry-run` resolves the assets, writes the checksums file and prints every attachment without a token, a repository slug or a network call; a tree with no matching artifact fails with a message that names the patterns.
- [x] #3 `automation -- release_rehearsal` fabricates the artifact tree a release would download (three wheels, a Conda package, both npm tarballs) and runs the same resolve → hash → publish path in `--dry-run`, so the rehearsal runs the code the release runs rather than a copy of its shell.
- [x] #4 A `Release rehearsal` job runs that command on every pull request and is part of the aggregate `checks` verdict, so a broken publish step fails the pull request instead of a release.
- [x] #5 Tests fail if the workflow grows its own expansion back, if a list parameter loses its list default, or if the publish path stops attaching `SHA256SUMS` beside the artifacts.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**The step became one command.** `automation/release/_publish.py` owns it:
`matched_assets` reads `ASSET_PATTERNS` (`dist/pypi/*/*.whl`, `dist/conda/*.conda`,
`npm/*.tgz`, `npm/*/*.tgz`), `publish` hashes them into the sums file, and
`publish_release` creates the release or reuses one a retried run already made,
then replaces same-named assets. `release.yml` now names that command and passes
no flags twice - its shell has no `assets=(...)` array, no loop and no `--paths`.
`github-release` stayed, because it is the explicit-asset form and its tests are
the contract for the create/upload half; it calls the same `publish_release`.

**Why `--dry-run` is the rehearsal.** The old step could not be rehearsed at
all: `github-release` calls the API as soon as it has a tag, so the only way to
run it was to cut a release. `publish --dry-run` resolves the same globs, writes
the same `SHA256SUMS` and prints `would attach <path> (<n> bytes)` for each file
plus `would publish the GitHub release <tag> as a release|prerelease with N
asset(s)` - no token, no slug, no network. `release_rehearsal` builds the tree a
release downloads under a temporary root (three wheels, a Conda package, both
npm tarballs under `bridge/` and `alias/`) and runs exactly that path, so the
rehearsal exercises the release's code rather than a copy of its shell. Both are
one record (`PublishRequest`) rather than a seven-argument function, per
decision-81.

**Where it runs.** `ci.yml` gained a `Release rehearsal` job that runs
`pixi run -e build automation -- release_rehearsal` in the `build` environment
the release publishes from, with the same lockfile, and `checks` now needs it -
so it is part of the aggregate verdict branch protection reads. It costs about
ten seconds: no install beyond the cached Pixi environment, no artifacts built,
no network.

**Tests.** `tests/scripts/test_release.py` gained seven: the dry run hashes
every artifact and attaches the sums with no token in the environment; an empty
tree fails with a message naming the patterns; the real path creates one release
and uploads every artifact plus `SHA256SUMS` last; a real publish without
credentials fails while a dry run does not; the rehearsal fabricates three
wheels, a `.conda` and both tarballs and publishes nothing; the workflow calls
`release_publish` once and carries no `--paths` and no `for asset in`; and the
rehearsal is a required job. Two helpers that patched `_verify` now patch
`_publish`, where the API calls live. `test_ci.py`'s aggregate-gate assertion
learned the new job.

**Evidence.** `doit release_rehearsal` prints the seven attachments and the
verdict and exits 0. Running the release's own command shape over a fabricated
tree in the checkout (`dist/pypi/kit/*.whl`, `dist/conda/*.conda`,
`npm/bridge/*.tgz`, `--out dist/SHA256SUMS`, `--dry-run`) resolves all four and
writes the sums with no token set. Mutation-checked: restoring the old shell
line in `release.yml` fails the workflow test, removing the sums from the upload
list fails the publish test, and dropping the list default fails the `doit`
contract test in `test_automation_cli.py`.

**Documentation impact.** No user-facing documentation changes: no package, CLI
user surface or wire payload moved - `publish`, `rehearsal` and the two tasks are
maintainer tooling, and `github-release` behaves as before. doc-14 gains the
rehearsal row in the gate table and a paragraph in the 0.11.0 record describing
what closed the gap the release exposed; no decision record was needed, since
decision-82 and TASK-35 already govern the gate and the train.
<!-- SECTION:NOTES:END -->
