---
id: TASK-103
title: >-
  Add i18n through Qt catalogues shared with the page and the accessibility rule
  UI005
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
updated_date: '2026-10-28 16:24'
labels: []
milestone: m-11
dependencies:
  - TASK-96
  - TASK-70
type: enhancement
ordinal: 103000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-60. qgis_sdk.i18n.tr used by the declarations and offered to authors; QTranslator from <plugin>/i18n/<locale>.qm for the QGIS locale, resolved when surfaces and descriptions are built; qgis-sdk i18n extract (declarations, author tr calls, web t()) into a .ts file and i18n compile into .qm plus a JSON catalogue served through qgis.host.i18n; I18N001 for a listed locale with no catalogue; accessible names and descriptions on every catalogue input, UI005, tab order by declaration, aria-* on the web components; QLocale/Intl formatting in Distance and Number.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A plugin with a Polish catalogue shows translated titles, menu paths, labels and notifications natively and on the page when QGIS runs in pl, and source strings otherwise; describe_plugin carries source strings plus locale (native + webengine tests).
- [ ] #2 extract/compile round-trip a fixture plugin's strings including web t() calls; I18N001 and UI005 fire on fixtures; every catalogue input exposes an accessible name (pure + native tests).
- [ ] #3 doc-12/doc-13 document the translator workflow with Qt Linguist and the accessibility rules; the example ships one translation.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ecosystem research: evaluate Qt tool discovery with actionable missing-tool diagnostics, unfinished translation reporting and deterministic check mode; keep native and web strings in the same catalog workflow.
<!-- SECTION:NOTES:END -->
