---
id: TASK-139
title: Keep internal APIs out of official user documentation
status: To Do
assignee: []
created_date: '2026-10-28 16:43'
labels: []
dependencies: []
references:
  - apps/docs/guides
  - apps/docs/scripts/generate.ts
  - apps/docs/astro.config.ts
priority: medium
type: docs
ordinal: 139000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit the official documentation and generated reference sources for implementation-only APIs that leak into user-facing docs. Present only supported public SDK interfaces as the authoring API; keep contributor implementation guidance clearly separated rather than removing useful contributor material. Coordinate the public inventory and stability tiers planned in TASK-97. Do not treat undocumented internals as supported or remove exported behavior as part of this docs task. No release milestone is assigned.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Define and apply an explicit public-versus-internal documentation boundary across Python and TypeScript based on exports and intended support; identify ambiguous cases for review rather than assuming all exported names are public.
- [ ] #2 Remove or relocate internal modules and implementation-only APIs from user-facing guides and reference pages while retaining necessary public APIs and marking contributor-only documentation clearly.
- [ ] #3 Fix the durable guide and generation sources so internals do not reappear on rebuild; preserve or redirect existing public links and do not break the contributor documentation.
- [ ] #4 Add automated checks or an explicit reviewable allowlist to catch internal API leaks and cover the generated output; run documentation tests and a production build and link checks.
<!-- AC:END -->
