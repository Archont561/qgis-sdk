---
id: decision-60
title: Translate declared strings through Qt catalogues shared with the page, and make accessible names a check rule
date: '2026-10-26'
status: accepted
---
## Context

Titles, menu paths, form labels, notifications, help texts and web pages are
all English source strings today; the catalogue and the hosts add many more.
QGIS users run localised installations and the plugin repository expects
translations for wide adoption. Accessibility has one rule (`objectName`),
which serves agents, not screen readers.

## Decision

1. **Source strings are translatable where they are declared.** `title=`,
   `@menu` paths, parameter labels and help, notification texts and
   catalogue labels go through `qgis_sdk.i18n.tr(text, context=)`
   implicitly: the declarations call it, authors call it for their own
   strings. `tr` resolves through a `QTranslator` the runtime loads from
   `<plugin>/i18n/<locale>.qm` for the QGIS locale (`locale/userLocale`),
   falling back to the source string. Nothing is translated at import
   time; resolution happens when a surface or description is built, so
   `describe_plugin` carries source strings plus a `locale` field.
2. **One catalogue for both sides.** `qgis-sdk i18n extract` writes a Qt
   `.ts` file from the declarations, author `tr` calls and the web source
   (`t()` from the bridge); `i18n compile` produces the `.qm` and a JSON
   catalogue the page loads through `qgis.host.i18n` (locale and strings),
   so one translator workflow serves native and web. `build` includes both;
   `check` reports `I18N001` for a missing locale the project lists.
3. **Accessibility.** Every catalogue input sets its accessible name from
   its label and its description from the help text; `UI005` reports an
   interactive widget without an accessible name; tab order follows
   declaration order; the web components use the same labels through
   `aria-*`. Right-to-left layouts are Qt's; the catalogue does not
   override direction.
4. **Numbers, units and dates** render through Qt's locale (`QLocale`) in
   the catalogue and `Intl` on the page; `Distance` shows the unit the
   project uses.

## Consequences

- Declarations stay plain; `tr` is a function, not a decorator.
- Translators get the standard Qt Linguist workflow; the page gets its
  catalogue for free.
- Tasks: TASK-103 in m-11 (startable after TASK-96).
