---
id: TASK-43
title: Publish a Starlight documentation site from the backlog guides
status: To Do
assignee: []
created_date: '2026-10-24 21:14'
updated_date: '2026-10-24 21:21'
labels: []
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
<!-- SECTION:NOTES:END -->
