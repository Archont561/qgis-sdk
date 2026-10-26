---
id: doc-20
title: M12 sprint train (tentative) and the 1.1.0 go/no-go
type: guide
created_date: '2026-10-26 09:20'
---
# M12 sprint train (tentative) and the 1.1.0 go/no-go

**Status:** Not started and not scheduled. [m-12](../../milestones/m-12%20-%201.1.0-%E2%80%94-deferred-native-compute-feasibility-(tenta.md) is a reservation for
deferred research, re-pointed from 0.7.0, 0.8.0 and 0.9.0 on 2026-10-26 to sit after 1.0;
nothing in it blocks any 0.x release, and nothing in it may start without the go/no-go below.
Sprint membership lives here and in the milestone body, not in task fields
([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

## 1. What has to be true before sprint 1

The go/no-go is a dated decision file (the next free decision id), accepted
by the owner, that answers three questions in writing:

1. **Which qualified workflow must the prototype beat, and by how much?** The
   reference workflow of TASK-22 is the candidate; "faster" without a
   measured baseline is not a target.
2. **What is the bridge delta?** Expected zero - a native backend changes
   what runs behind Python, not what crosses `QWebChannel` - but stated
   against the prototype's result schema, not assumed. A result shape that
   leaks a native handle is a contract change and is refused under
   [decision-9](../../decisions/decision-9%20-%20Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md).
3. **What does a no-go look like?** A written outcome that closes TASK-10
   and TASK-71 as "not released" is a valid, complete end of this milestone.

## 2. Dependency read

| Task | Declared dependencies | State |
| --- | --- | --- |
| [TASK-10](../../tasks/task-10%20-%20Prototype-an-optional-Rust-algorithm-backend-after-v1.md) optional Rust backend prototype | TASK-22 ✓, TASK-31 ✓, renewed approval | To Do, deferred |
| [TASK-71](../../tasks/task-71%20-%20Prepare-and-qualify-1.1.0-release-tentative-deferred-target-post-1.0.md) 1.1.0 gate (tentative) | TASK-10, TASK-107 | To Do, deferred |

## 3. Sprint train (tentative)

- **Sprint 0: the go/no-go decision.** No code. Produces the decision file,
  the measured baseline and the bridge-delta statement.
- **Sprint 1: TASK-10 as a time-boxed spike.** One pull request, one
  evidence document under `backlog/docs/plans/` in the shape of doc-5/doc-6,
  a written outcome either way. The prototype never lands in
  `qgis_sdk.reference`; it lives beside the example until the outcome says
  otherwise.
- **Gate: TASK-71.** Only if the outcome is go; otherwise closed with the
  no-go recorded. No artifact is stamped or published while the milestone
  stays tentative.
