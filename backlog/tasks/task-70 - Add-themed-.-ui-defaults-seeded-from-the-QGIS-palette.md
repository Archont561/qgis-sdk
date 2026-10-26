---
id: TASK-70
title: Add themed ./ui defaults seeded from the QGIS palette
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
labels: []
milestone: m-6
dependencies:
  - TASK-69
  - TASK-64
type: enhancement
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-46 point 4 and decision-16's theme half, narrowed to palette tokens. A ./ui entry with a small set of form controls (button, input, select, checkbox, field row, notice) styled through CSS variables (--qgis-sdk-accent, --qgis-sdk-bg, --qgis-sdk-fg, spacing, font); host() reads the running QGIS palette when the page opens and sets the variables on the document root, so a page looks native by default and is overridable by CSS. Rich declarative themes stay out.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ./ui controls render with the variables and fall back to documented defaults without a host; a Storybook theme switcher shows the QGIS light and dark palettes (bun tests).
- [ ] #2 Inside QGIS the page's variables match the running palette (webengine test reading computed styles); the scaffold templates opt in through one import; the published tarball includes ./ui types and CSS.
- [ ] #3 decision-16 is promoted with a status review naming the palette tokens as the theme surface; doc-13 documents the variables.
<!-- AC:END -->
