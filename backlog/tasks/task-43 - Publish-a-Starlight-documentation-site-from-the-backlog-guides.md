---
id: TASK-43
title: Publish a Starlight documentation site from the backlog guides
status: In Progress
assignee: []
created_date: '2026-10-24 21:14'
updated_date: '2026-10-27 16:53'
labels: []
milestone: m-6
dependencies: []
references:
  - >-
    backlog/decisions/decision-29 -
    Keep-READMEs-minimal-and-hold-reference-prose-in-backlog-guides-until-the-docs-site.md
  - backlog/docs/guides/doc-12 - qgis-sdk-Python-package-guide.md
  - backlog/docs/guides/doc-13 - qgis-sdk-TypeScript-package-guide.md
  - >-
    backlog/docs/guides/doc-14 -
    Workspace-development-qualification-harnesses-and-evidence.md
priority: medium
type: docs
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Stand up an Astro Starlight site (the pixi-sandbox docs are the model: docs/ in the workspace, built by a docs workflow, deployed to GitHub Pages) whose pages are rendered from the backlog guides doc-12, doc-13 and doc-14 rather than from the READMEs. decision-29 keeps every README minimal - pitch, install, one example, pointers - so the site is where the reference prose, the qualification evidence and the migration notes are read. Until it exists the guides under backlog/docs/guides/ are the readable source. Focused checks are part of this task: a link check over the rendered site and a drift check that no README grows a reference section again.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An Astro Starlight site under docs/ (or apps/docs) builds from Bun in the pinned workspace and renders the Python guide, the bridge guide and the workspace/qualification guide as pages with working internal links.
- [ ] #2 A docs workflow builds the site on pull requests and deploys it to GitHub Pages from main; the root README carries the docs badge and link, as pixi-sandbox does.
- [x] #3 Every README stays within the decision-29 shape (pitch, install, one example, pointers) and a check in tests/scripts fails when a README reintroduces a reference section.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: AC #3 pulled forward, it needed no site. tests/scripts/test_readme_shape.py (release-tool suite) holds each README to one H1, the decision-29 section set (Installation, Try it, Example, Develop, Documentation, License), no subsections, an 80-line budget, and a link to a backlog guide; it rejects the former 870-line package README on two counts. AC #1 and #2 remain the Starlight site itself.

Joined m-6 (0.7.0) on 2026-10-26: the Storybook static build of decision-46 publishes with this site.

2026-10-27: apps/docs (Astro 7.4 + Starlight 0.42, built under Bun) renders doc-12/13/14 one page per H2 through scripts/generate.ts (links rewritten, headings demoted, editUrl and lastUpdated from the guide), with start pages, a splash landing, brand.css, robots.txt, sitemap and llms.txt/.md twins (starlight-llms-markdown), the qgis-sdk-ui Storybook under /storybook/, a zero-dependency link check over dist/ and Bun tests at 90% coverage. Pixi tasks docs-build, docs-link-check, docs-dev; .github/workflows/docs.yml builds and link-checks on PRs and deploys to GitHub Pages from main. Root README carries the docs badge and link. AC #1 proven locally (68 pages, 5804 internal links, 0 broken); AC #2 awaits the first deploy from main.
<!-- SECTION:NOTES:END -->
