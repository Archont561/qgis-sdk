---
id: TASK-165
title: Put the compatibility on the landing page, sync the Storybook theme, and make the first-plugin guide a single walk
status: In Progress
assignee: []
created_date: '2026-11-10 10:20'
labels: []
dependencies: []
ordinal: 165000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A reader lands on a page that never states which QGIS and Python it works on, opens a Storybook that ignores the theme they chose, and follows a first-plugin guide that hands them off to four other pages mid-walk. State the compatibility where they land, take it from the support matrix, follow the site theme in Storybook, and make the guide a single page with real command output replayed in place.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The landing page and the install page state the qualified QGIS series and Python range, read from the support matrix rather than written by hand.
- [x] #2 The notice says what is not covered ("nothing else is tested") and links to the qualified rows.
- [x] #3 The Storybook manager and preview follow the documentation theme, with the OS preference as the fallback and the toolbar still able to override.
- [x] #4 /start/first-plugin/ runs install, scaffold, declare, test, check, dev and build on one page, with real command output, and links only at the end.
- [x] #5 The scaffold walk is an interactive file tree and the check walk is an animated transcript, both replayable and both readable under prefers-reduced-motion.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision-79 records the choices. `apps/docs/tests/compat.test.ts` holds the matrix parser; the walkthrough transcripts were captured from `qgis-sdk new my_tools --title "My Tools" --no-input`, `qgis-sdk test`, `qgis-sdk check` and `qgis-sdk build` on this tree.
<!-- SECTION:NOTES:END -->
