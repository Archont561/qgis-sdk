---
id: TASK-104
title: >-
  Version plugin settings with migrations, add first-run, upgrade and reset
  hooks, and document runtime isolation
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-67
type: enhancement
ordinal: 104000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-61. settings_version on the plugin class; @migration(from_version, to_version) functions run in order on start through a SettingsMigration over the plugin prefix, failing the start by name without touching the stored version; on_first_run / on_upgrade(previous) / on_reset hooks; ResetAction catalogue surface clearing prefix, owned temporary outputs and the first-run marker; owned outputs registered under the prefix; runtime isolation per plugin (vendored runtime, import rewrite, coexistence harness) documented as the supported installation; describe_plugin gains settings_version.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Migrations run in order exactly once per profile, a failing migration refuses the start and leaves the version stored, and the hooks fire on first run, upgrade and reset with the fakes and natively (pure + native tests).
- [ ] #2 ResetAction clears the prefix, the registered temporary outputs and the marker; two plugins on different runtime versions coexist in one QGIS with the harness unchanged (coexistence harness).
- [ ] #3 doc-12 documents settings versioning, the hooks, what reset removes, and that QGIS offers no uninstall hook.
<!-- AC:END -->
