---
id: TASK-122
title: Design injectable worker-job dependencies and test overrides
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies:
  - TASK-115
priority: medium
type: feature
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner wants jobs using third-party libraries such as pandas to be straightforward to test with fake dependencies. Explore SDK-owned FastAPI-inspired Annotated[Protocol, Depends(provider)] or a similarly typed API; neither Depends nor dependency injection currently exists. Exact syntax and release target are unchosen. Do not require FastAPI or Pydantic.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide and document the public syntax, how dependency parameters are excluded from job input schemas, type checking, direct unit invocation, provider scopes and cleanup, overrides, cycle and missing dependency errors.
- [ ] #2 Ensure provider resolution runs in the worker for each attempt where appropriate; worker-safe capability restrictions, cancellation, thread affinity and concurrent override isolation are explicit and tested.
- [ ] #3 Prove an ordinary job can use a pandas-backed adapter in production and a lightweight fake in tests without making pandas an SDK runtime requirement; document dependency provisioning separately.
<!-- AC:END -->
