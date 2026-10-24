---
id: TASK-37
title: >-
  Add milestone-triggered autorelease and CI optimizations from playtest
  patterns
status: Done
assignee: []
created_date: '2026-10-24T08:55:00Z'
updated_date: '2026-10-24 09:39'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    https://github.com/Archont561/playtest/blob/main/.github/workflows/auto-release.yml
  - >-
    https://github.com/Archont561/playtest/blob/main/.github/workflows/release.yml
  - >-
    https://github.com/Archont561/playtest/blob/main/.github/workflows/publish-sandbox.yml
  - 'https://github.com/Archont561/pixi-sandbox/issues/179'
  - 'https://github.com/Archont561/pixi-release/issues/8'
priority: high
type: chore
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement milestone-triggered autorelease (milestone-v*, milestone/*, m-v* tag pushes) and CI cost/latency optimizations observed in Archont561/playtest.

Key patterns from playtest auto-release.yml:
- Milestone tag triggers: milestone-v*, milestone/*, m-v* alongside push to main
- paths-ignore for docs/backlog/agent/devcontainer-only changes
- concurrency group (cancel-in-progress: false to protect release train)
- workflow_dispatch with scope, bump, dry-run inputs
- scripts/detect_release.py for convco-style change detection
- Scope-specific quality gates (rust, python, typescript, go, java, cpp, c, csharp, r)

Optimization techniques from pixi-sandbox issue #179 (implemented in playtest publish-sandbox.yml):
- Direct curl + SHA256SUMS verification instead of double pixi install + fetch-release
- Skip dedicated plan job VM for static targets
- concurrency groups with cancel-in-progress
- Path-filtered triggers (paths-ignore) to skip docs-only runs

Apply to qgis-sdk:
- Add milestone tag triggers to .github/workflows/autorelease.yml
- Add paths-ignore to skip backlog/docs-only pushes
- Verify concurrency and OIDC permission patterns match playtest
- Add milestone gate: pre-release quality gates before cutting release tags from milestone tags
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 autorelease.yml triggers on milestone-v*, milestone/*, m-v* tag pushes in addition to main
- [x] #2 autorelease.yml uses paths-ignore to skip backlog/docs-only changes
- [x] #3 autorelease.yml has concurrency group protecting the release train
- [x] #4 workflow_dispatch supports scope, bump, dry-run inputs like playtest
- [x] #5 release.yml tag patterns support scoped tags (scope-v*, scope/*)
- [x] #6 publish-sandbox.yml uses direct curl + SHA256SUMS instead of double pixi install
- [x] #7 release.yml uses OIDC id-token: write for trusted publishing
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: Updated pixi-sandbox.toml ([workflow] push_paths + relock_paths) and regenerated .github/workflows/publish-sandbox.yml, .github/workflows/relock.yml, and scripts/restore.sh via pixi-sandbox 0.8.0 init (matching Archont561/pixi-sandbox-starter: direct curl + SHA256SUMS bootstrap, concurrency group, setup-pixi v0.11.2; pixi-sandbox init --script-path scripts/restore.sh --check exit 0). Extended scripts/release.py and .github/workflows/autorelease.yml + .github/workflows/release.yml with milestone tag triggers (milestone-v*, milestone/*, m-v*), paths-ignore (backlog/**, .agents/**, .devcontainer/**, *.md), workflow_dispatch inputs (scope, bump, dry-run, version, suffix), scope-aware pre-release quality gates and dry-run packaging checks, scoped release tag classification (v*, *-v*, */*v* with milestone exclusions), and top-level + job-level OIDC id-token: write permissions. Verified locally: 107/107 tests in test-release-tool, actionlint exit 0, ruff check/format exit 0, biome check exit 0, typecheck exit 0, bun run test --force (0 cached) and bun run coverage (100% Python + TypeScript) green.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Aligned pixi-sandbox.toml, publish-sandbox.yml, relock.yml, scripts/restore.sh, .devcontainer/setup.sh, and .gitignore with Archont561/pixi-sandbox-starter (0.8.0 single-step curl + SHA256SUMS bootstrap, concurrency group, setup-pixi v0.11.2, and path-filtered push/relock triggers; pixi-sandbox init --check exit 0). Implemented TASK-37 across scripts/release.py, .github/workflows/autorelease.yml, .github/workflows/release.yml, and tests/scripts/test_release.py: milestone tag triggers (milestone-v*, milestone/*, m-v*), paths-ignore, workflow_dispatch inputs (scope, bump, dry-run, version, suffix), scope-aware pre-release quality gates and dry-run packaging checks, scoped release tag support (v*, *-v*, */*v* with milestone exclusions), and OIDC id-token: write permissions. All 107 release-tool tests, actionlint, ruff, biome, typecheck, and 100% coverage gates pass locally (GitHub Actions runners remain unavailable per doc-8).
<!-- SECTION:FINAL_SUMMARY:END -->
