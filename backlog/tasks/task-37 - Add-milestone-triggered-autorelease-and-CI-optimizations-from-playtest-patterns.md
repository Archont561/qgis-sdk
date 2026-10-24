---
id: TASK-37
title: >-
  Add milestone-triggered autorelease and CI optimizations from playtest
  patterns
status: To Do
assignee: []
created_date: '2026-10-24T08:55:00Z'
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
  - https://github.com/Archont561/pixi-sandbox/issues/179
  - https://github.com/Archont561/pixi-release/issues/8
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
- [ ] #1 autorelease.yml triggers on milestone-v*, milestone/*, m-v* tag pushes in addition to main
- [ ] #2 autorelease.yml uses paths-ignore to skip backlog/docs-only changes
- [ ] #3 autorelease.yml has concurrency group protecting the release train
- [ ] #4 workflow_dispatch supports scope, bump, dry-run inputs like playtest
- [ ] #5 release.yml tag patterns support scoped tags (scope-v*, scope/*)
- [ ] #6 publish-sandbox.yml uses direct curl + SHA256SUMS instead of double pixi install
- [ ] #7 release.yml uses OIDC id-token: write for trusted publishing
<!-- AC:END -->
