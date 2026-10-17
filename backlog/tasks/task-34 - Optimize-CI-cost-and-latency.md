---
id: TASK-34
title: Optimize CI cost and latency
status: In Progress
assignee: []
created_date: '2026-10-17 18:10'
updated_date: '2026-10-17 18:29'
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
- [ ] #1 Cross-platform jobs cache Python and Bun dependency layers, with warm-run job times captured in the task notes and compared against the PR #14 baseline.
- [ ] #2 Pushing a new commit to an open PR cancels the in-progress run for the superseded head, verified in the Actions UI or API.
- [ ] #3 Fresh workflow runs emit no action-runtime deprecation warnings, after upgrading actions/checkout, actions/setup-python and oven-sh/setup-bun as needed.
- [ ] #4 The tested surface is unchanged: same suites and OS matrix, coverage gates still single-sourced on the checks job, and pixi lock --check still green; any scope change such as path filters or matrix narrowing requires an explicit decision note with rationale.
- [ ] #5 The task closes with before/after wall-clock and estimated billing numbers, keeping or reverting each change based on those numbers.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Created 2026-10-17 at user request alongside the cross-platform CI job (PR #14). Cost context: GitHub-hosted runners bill macOS at 10x and Windows at 2x the per-minute Linux rate, so caching and cancellation pay for themselves quickly as the matrix stays in place.
<!-- SECTION:NOTES:END -->
