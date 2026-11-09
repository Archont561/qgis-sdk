---
id: TASK-160
title: Migrate the documentation site from Starlight to Fumadocs on Next
status: In Progress
assignee: []
created_date: '2026-11-09 18:31'
labels: []
dependencies: []
references:
  - >-
    backlog/decisions/decision-73 -
    Render-the-documentation-site-with-Fumadocs-on-Next-and-keep-the-export-static.md
  - >-
    apps/docs/guides/doc-14 -
    Workspace-development-qualification-harnesses-and-evidence.md
priority: medium
type: docs
ordinal: 160000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the Astro Starlight renderer of apps/docs with a Fumadocs site on Next, statically exported to out/ and uploaded to GitHub Pages exactly as dist/ was. The content pipeline, the routes, the compatibility pages, the link check and the Bun suites survive the move; what changes is the renderer, the sidebar (meta.json instead of Starlight frontmatter), the llms surface (written and gated by scripts/postbuild.ts instead of starlight-llms-markdown) and search (a static index exported at build time). decision-73 records the choice and its consequences, including the Node runtime the docs job now needs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 apps/docs builds with Next output: export into out/ and publishes every URL the Starlight site published, with the legacy and migration redirects and every internal link resolving.
- [ ] #2 llms.txt, llms-full.txt and a .md export per page are written by the build, and the build fails when a rendered page has no markdown twin or is missing from the index.
- [ ] #3 Search works with no server: the index is exported at build time and the dialog searches it in the browser.
- [ ] #4 The link check and the Bun suites pass over the exported tree, and their coverage stays above the workspace's 90%.
- [ ] #5 The docs workflow deploys apps/docs/out and the contributor guide in doc-14 describes the Fumadocs pipeline, the static export and the Node prerequisite.
<!-- AC:END -->
