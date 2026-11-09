---
id: TASK-160
title: Migrate the documentation site from Starlight to Fumadocs on Next
status: Done
assignee: []
created_date: '2026-11-09 18:31'
updated_date: '2026-11-09 20:02'
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
- [x] #1 apps/docs builds with Next output: export into out/ and publishes every URL the Starlight site published, with the legacy and migration redirects and every internal link resolving.
- [x] #2 llms.txt, llms-full.txt and a .md export per page are written by the build, and the build fails when a rendered page has no markdown twin or is missing from the index.
- [x] #3 Search works with no server: the index is exported at build time and the dialog searches it in the browser.
- [x] #4 The link check and the Bun suites pass over the exported tree, and their coverage stays above the workspace's 90%.
- [x] #5 The docs workflow deploys apps/docs/out and the contributor guide in doc-14 describes the Fumadocs pipeline, the static export and the Node prerequisite.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-12 (closure): PR #180 merged as 8692746. docs workflow run 42688317062 on main ran 'build and check the site' (9420 internal links on 142 pages, 0 broken; 98 markdown exports; 99 routes; 38 compatibility pages) and 'deploy to GitHub Pages' to success, so the Fumadocs export is live at https://archont561.github.io/qgis-sdk/ with llms.txt, llms-full.txt, one .md per page and the Storybook under /storybook/. Four defects were fixed on the way: @types/node was missing from apps/docs, so next build tried to install it with Corepack-guarded yarn; the Storybook nav entry is an external link and carried no basePath; the guide tests still read apps/docs/src/content/docs; and the move had turned a fixture call into `["open_fixture"](/)`. The documentation layer above the site - policy, indexes and the three prose checks - is TASK-161 and decision-74.
<!-- SECTION:NOTES:END -->
