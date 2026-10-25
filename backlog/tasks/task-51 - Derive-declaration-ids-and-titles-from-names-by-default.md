---
id: TASK-51
title: Derive declaration ids and titles from names by default
status: In Progress
assignee:
  - '@agent'
created_date: '2026-10-25T09:29:00Z'
updated_date: '2026-10-25T09:29:00Z'
labels: []
milestone: m-3
dependencies: []
type: feature
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make `id=` and `title=` optional on every declaration decorator. A class id derives from the snake_case class name plus a six-hex-digit hash of module and qualname (deterministic, never random: the bridge, the generated client and the fingerprint depend on stable ids); a method id is the plain method name; titles come from the name. Explicit values still win and are validated at decoration time. decision-30.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `@plugin`, `@action`, `@algorithm`, `@job` and `@provider.algorithm` work bare and with partial keywords; `@stream` needs only `events=`
- [ ] #2 Derived class ids are stable across imports, differ between same-named classes, and derived method ids are plain identifiers
- [ ] #3 Explicit invalid ids and titles are still refused before the class exists; the id grammar and schema version do not move
- [ ] #4 doc-12 documents the rules and carries a migration note; decision-30 records why deterministic; task listed in the doc-4 0.4.0 inventory
<!-- AC:END -->
