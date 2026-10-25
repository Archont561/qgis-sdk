---
id: TASK-34
title: Optimize CI cost and latency
status: Done
assignee: []
created_date: '2026-10-17 18:10'
updated_date: '2026-10-22 01:43'
labels: []
milestone: m-0
dependencies: []
references:
  - .github/workflows/ci.yml
  - >-
    backlog/decisions/decision-17 -
    Deliver-a-qualified-Python-first-vertical-slice-for-v1.md
  - backlog/tasks/task-33 - Qualify-Windows-macOS-and-Desktop-QGIS-targets.md
priority: medium
type: chore
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The cross-platform matrix job (macos-latest, windows-latest) added alongside this task roughly triples the CI surface on every push, and GitHub bills macOS minutes at 10x and Windows at 2x the Linux rate. Baseline from PR #14 run 39055033648: checks 1m15s, cross-platform (macos-latest) 32s, cross-platform (windows-latest) 1m39s of job time, before provisioning overhead. The workflows currently configure no dependency caching, no cancellation of superseded runs, and pull action versions that emit Node 20 runtime deprecation warnings. Candidates: cache pip and Bun dependency layers on the cross-platform jobs; add a concurrency group with cancel-in-progress; upgrade actions/checkout, actions/setup-python and oven-sh/setup-bun to supported runtimes; skip or trim jobs for changes that cannot affect the suites (for example docs-only pushes); single-source the Bun version pin shared by the workflow and packageManager. Non-goals: changing what is tested or where the coverage gates live, narrowing or widening the OS matrix without an explicit decision (ADR-17 keeps v1 at Windows and Linux x86-64), and QGIS target qualification (TASK-33).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Cross-platform jobs cache Python and Bun dependency layers, with warm-run job times captured in the task notes and compared against the PR #14 baseline.
- [x] #2 Pushing a new commit to an open PR cancels the in-progress run for the superseded head, verified in the Actions UI or API.
- [x] #3 Fresh workflow runs emit no action-runtime deprecation warnings, after upgrading actions/checkout, actions/setup-python and oven-sh/setup-bun as needed.
- [x] #4 The tested surface is unchanged: same suites and OS matrix, coverage gates still single-sourced on the checks job, and pixi lock --check still green; any scope change such as path filters or matrix narrowing requires an explicit decision note with rationale.
- [x] #5 The task closes with before/after wall-clock and estimated billing numbers, keeping or reverting each change based on those numbers.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Created 2026-10-17 at user request alongside the cross-platform CI job (PR #14). Cost context: GitHub-hosted runners bill macOS at 10x and Windows at 2x the per-minute Linux rate, so caching and cancellation pay for themselves quickly as the matrix stays in place.

TASK-34 measurement pass (2026-10-17, PR #15, branch arena/8a84c609-qgis-sdk).

Baseline (PR #14 run 39055033648, job time): checks 1m15s, cross-platform (macos-latest) 32s, cross-platform (windows-latest) 1m39s; run wall 1m42s. Estimated billing 9.9 Linux-equivalent minutes (checks 1.25x1 + macOS 5.33x10 + Windows 3.30x2).

Changes, all in .github/workflows/ci.yml:
- Concurrency group `${{ github.workflow }}-${{ github.head_ref || github.ref }}` with cancel-in-progress everywhere except the default branch, where runs queue so a landed commit's result is never discarded mid-run.
- pip download cache via setup-python `cache: pip` keyed on packages/qgis-sdk-python/pyproject.toml, and a Bun install store cache via actions/cache@v6 keyed on bun.lock (setup-bun only caches the Bun executable).
- Node 24 actions: checkout v4->v7, setup-python v5->v7, codecov-action v5->v7 (v5 embedded github-script@60a0d83 v7.0.1 on node20, the last deprecation source in checks). setup-bun@v2 already resolves to v2.2.0 on node24, so no bump was needed.

Cold run (first run, populates caches): 39058323856, wall 1m46s, success; jobs checks 57s, macOS 35s, Windows 1m41s.

Warm runs (commit 5055ded, caches restored; job times):
- PR run 39058815847 (like-for-like with the baseline PR run): checks 1m6s, macOS 20s, Windows 1m5s. Sum 151s vs baseline 206s (-27%); estimated billing 6.6 Linux-equivalent minutes (-33% vs 9.9).
- Push run 39058811718: checks 1m10s, macOS 41s, Windows 1m23s. Sum 194s; the macOS 41s is a slow-runner outlier against the same commit's 20s - the small macOS job varies roughly 20-41s run to run, so single samples should not be over-read.
- Step evidence: Windows pip install 45s -> 21s, macOS 11s -> 5s; Bun install 11s -> 10s (Windows) - the Bun store cache is latency-neutral at today's dependency size. Decision: keep it anyway for registry independence and headroom as the workspace grows (~80-100 MB per OS, well inside the 10 GB per-repo cache budget); its value scales with the download layer while pip carries the wall-clock win today.
- Run wall-clock is queue-dominated (the warm PR run waited ~50s for a macOS-capacity-constrained runner), so job time is the comparison metric, matching how the baseline was recorded.

Cancellation evidence: pushing 5055ded while PR run 39058772930 (head 3f256be) was in flight ended it with API conclusion=cancelled (checks and Windows stopped mid-job; macOS had just finished). Superseded heads no longer burn a full matrix; default-branch runs are exempt from cancellation by design.

Deprecation evidence: the baseline named actions/checkout@v4 and actions/setup-python@v5 on both cross-platform jobs and actions/github-script@60a0d83 (via codecov@v5) on checks. Fresh runs 39058811718 and 39058815847 carry zero Node 20 deprecation annotations, verified through the checks/annotations API (job log blobs are unreadable from this sandbox).

Scope held (TASK-34 AC 4): suites, OS matrix, and coverage gates (single-sourced on checks, Codecov uploads untouched) are unchanged; no path filters or matrix narrowing were added; `pixi lock --check` is green on PR #15 (relock run 39058815845: lock guard success, no drift).

Keep/revert ledger (AC 5): keep pip cache (measured win), keep Bun cache (latency-neutral, kept with rationale above), keep concurrency group (verified), keep checkout/setup-python/codecov upgrades (zero-warning requirement), no change to setup-bun (already node24).

Second pass (2026-10-22, branch arena/f9eacfee-qgis-sdk, PR pending): the two items
AC 4 explicitly left open as follow-ups are now partly taken - ci.yml gained
`paths-ignore: backlog/**, AGENTS.md` on both triggers and `push: branches: [main]`
(pull_request already tests every proposal, so reacting to push on the same branch
billed the matrix twice per push), and cross-platform now carries
`if: github.event_name != 'push'`, so a merge to main no longer re-bills macOS at 10x
and Windows at 2x for a tree the PR proved. `checks` stays unconditional on main
because release tooling reads its coverage artifact and commit provenance. Matrix
narrowing (dropping an OS) is still refused: that removes compatibility evidence,
which is a policy change and not a caching trick.

Cost hygiene in the hand-written workflows: every job in ci.yml, release.yml and
autorelease.yml got `timeout-minutes` (the whole workspace previously had exactly one,
relock.yml's `verdict: 65`, so everything else inherited the 360-minute default).
autorelease dropped `prefix-dev/setup-pixi` and calls `python3 -m qgis_sdk_release
plan|tag` with `PYTHONPATH=packages/qgis-sdk-release/src`: the package declares no
dependencies, needs only Python >= 3.11, and shells out to nothing but `git`, so
installing a 279 MB environment to answer "no release is due" on every push to main
was pure overhead. `release.yml`'s `pypi` job gates checkout + setup-pixi on
`needs.build.outputs.prerelease == 'true'`, because that environment exists only for
the dry-run verify step.

Two proposals measured, then rejected with evidence. Merging the two Codecov uploads
into one `files:` list looks free, but codecov.yml scopes each `status.project` target
to its own flag and a combined upload would let both reports reach both flags - the
gate is worth more than the ~20s step. Splitting `checks` into more parallel jobs was
already rejected by AC 4 and stays rejected: each job re-pays checkout, setup and
cache restore.

relock.yml and publish-sandbox.yml are generated ("Regenerate this file instead of
editing it"), so they were not hand-patched; publish-sandbox is the only workflow in
the repo with no `concurrency:` block and no paths filter, and runs a multi-OS pack on
every push to main - both asks belong upstream in pixi-sandbox.

Verification limit, stated plainly: the Actions spending limit is exhausted until the
next billing cycle, so no run here was executed by CI. Evidence is local only -
`actionlint .github/workflows/*.yml` exit 0, YAML round-trip of every edited job's
`timeout-minutes`/`if`/`paths-ignore`, `python3 -m qgis_sdk_release plan --trigger push
--json` printing the documented `skip` on CPython 3.11.2 and 3.14, and a repo-wide
grep proving no test or lint target reads `backlog/**`. Whether the path gates skip
cleanly instead of leaving required checks pending needs the first post-restoration
run.

Recorded on the branch that takes it: PR #32. Pushing this note was also an experiment, and it
corrected a claim written here. Measured against the live runs API on 2026-10-22, while the billing
block left every job at zero steps but still recorded the events:

- `push: branches: [main]` works. Neither push on PR #32 produced a `push`-event `CI` run, while the
  previous branch's backlog-only push (e5bacbf) did bill a full `CI | push` run under the old bare
  `push:` trigger. The duplicate matrix per push is gone.
- `cross-platform`'s `if: github.event_name != 'push'` is accepted and evaluates true for
  `pull_request`: both host jobs exist for both PR heads. They never started only because the
  spending limit blocks job start (steps=0, "recent account payments have failed").
- `paths-ignore` on a `pull_request` filter does not look at the pushed commit: it evaluates the
  whole base...head diff, so a backlog-only commit inside a mixed pull request still runs CI.
  Consequence for the maintainer: a pull request whose entire diff is `backlog/**` or `AGENTS.md`
  gets no `ci.yml` run at all, so a branch-protection rule requiring `checks` can never be satisfied
  by such a pull request - it needs one non-ignored file, or an admin merge.

<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged to main in PR #15 (merge commit 5426c63, 2026-10-17). CI now caches pip downloads and the Bun install store on the cross-platform jobs, cancels superseded branch/PR runs while default-branch runs queue, and runs every action on node24 (checkout v7, setup-python v7, codecov-action v7; setup-bun@v2 already node24). Measured against the PR #14 baseline (run 39055033648: checks 1m15s, macOS 32s, Windows 1m39s, ~9.9 Linux-equivalent billed minutes): warm PR run 39058815847 posted checks 1m6s, macOS 20s, Windows 1m5s (151s job-time sum, -27%) at ~6.6 Linux-equivalent billed minutes (-33%); Windows pip install fell 45s to 21s. Cancellation verified on run 39058772930 (conclusion=cancelled after a superseding push); fresh runs carry zero Node 20 deprecation annotations; suites, OS matrix, coverage gates and pixi lock --check unchanged/green. Post-merge main run 39060970680 passed with zero deprecation annotations.
<!-- SECTION:FINAL_SUMMARY:END -->
