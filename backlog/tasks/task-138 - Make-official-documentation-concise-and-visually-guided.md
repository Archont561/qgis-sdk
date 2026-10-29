---
id: TASK-138
title: Make official documentation concise and visually guided
status: To Do
assignee: []
created_date: '2026-10-28 16:43'
updated_date: '2026-10-29 09:11'
labels: []
dependencies: []
references:
  - apps/docs/guides
  - apps/docs/src/content/docs
  - apps/docs/scripts/generate.ts
  - apps/docs/src/content/docs/start/first-plugin.md
  - apps/docs/src/content/docs/start/concepts.md
  - apps/docs/src/content/docs/guides/test-a-plugin.md
priority: medium
type: docs
ordinal: 138000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rewrite the official documentation to reduce verbosity and make concepts and workflows easier to scan using useful icons and components rather than large blocks of text. Review the hand-written site and durable guide sources as well as their generated pages. Coordinate the framework mosaic in TASK-130 and the first-plugin story in TASK-135 rather than duplicate them. No release milestone is assigned.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Audit reader-facing pages for repetition and dense prose and rewrite them into concise task-oriented content with clear headings and practical examples while retaining necessary accuracy and safety qualifications.
- [ ] #2 Use appropriate reusable visual components such as labeled icon cards or diagrams when they clarify relationships or workflows; provide meaningful text alternatives and keyboard access and sufficient contrast and responsive layouts.
- [ ] #3 Preserve searchable text and complete API details and command examples; move deeper material to appropriate reference pages instead of losing essential information or relying on icons alone.
- [ ] #4 Edit durable sources rather than generated output and preserve or redirect existing URLs; test representative components and navigation and run the docs build and internal link checks.
- [ ] #5 Provide a reusable workflow component for install through build with copyable commands and accurate working directories; reuse it across the homepage and relevant getting-started guides without duplicating guidance.
- [ ] #6 Provide an explorable scaffold file tree with concise file purposes and previews appropriate to the chosen scaffold options; derive or test the displayed files against actual scaffold output and coordinate with the terminal preview in TASK-136.
- [ ] #7 Provide an accessible test-target comparison for pure and QGIS and Desktop and web tests that states prerequisites and what each proves; explicitly distinguish fakes from native QGIS qualification.
- [ ] #8 Explain how Python declarations relate to actions and native UI and the web bridge and Processing through a labelled architecture flow with text alternatives and links to precise reference material.
- [ ] #9 Make the native and web component catalogues easier to explore through searchable or otherwise navigable entries with examples and availability; link suitable Storybook demonstrations and retain complete searchable property and behavior reference.
- [ ] #10 Evaluate a filterable support matrix and installation command tabs and job lifecycle diagrams where they clarify the guides; preserve qualification status and evidence and copyable commands and exact cancellation and scope semantics.
- [ ] #11 Reuse existing Starlight cards and steps and tabs where suitable; design a tested durable MDX or generation approach for reusable components in the generated guides instead of editing generated pages.
- [ ] #12 Coordinate the framework selector with TASK-130 and diagnostic rule cards with TASK-132; preserve stated limitations and do not claim the unresolved safety issues in TASK-118 or TASK-119 are fixed.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Coordinate the first-plugin walkthrough with TASK-135: apps/docs/src/content/docs/start/first-plugin.md is its durable source, with source-excerpt and scaffold-command regression tests in packages/qgis-sdk-python/tests/test_first_plugin_guide.py. Link or reuse it rather than duplicating the action or file tree.
<!-- SECTION:NOTES:END -->
