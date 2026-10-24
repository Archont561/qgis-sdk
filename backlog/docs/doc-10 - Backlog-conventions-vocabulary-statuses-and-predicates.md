---
id: doc-10
title: 'Backlog conventions: vocabulary, statuses and predicates'
type: guide
created_date: '2026-10-24 14:30'
---
# Backlog conventions: vocabulary, statuses and predicates

**Status:** Conventions, not scope. Nothing here changes a commitment, and every
rule below is derived from what this repository already does — where a rule
differs from current practice, the document says so and why.

**Purpose:** the board is maintained mostly by agents across sessions. Without a
fixed vocabulary two sessions will model the same work differently, and the next
one cannot tell drift from intent. This is the reference for those decisions.

Counts and states here were read on **2026-10-24** at `1d956a8` (after `v0.1.1`).

## 1. The five record classes

| Class | Prefix | Location | Lifecycle field |
| --- | --- | --- | --- |
| Task | `TASK-N`, `TASK-N.M` | `backlog/tasks/` | `status`: To Do / In Progress / Done |
| Milestone | `m-N` | `backlog/milestones/` | none — closed by its release task |
| Document | `doc-N` | `backlog/docs/{plans,specifications}/` or `backlog/docs/` | none |
| Decision | `decision-N` | `backlog/decisions/` | `status`: proposed / accepted |
| Draft | created with `--draft` | `backlog/drafts/` | promoted into a task |

Only tasks carry execution metadata (`priority`, `type`, `dependencies`,
`references`, `ordinal`, `milestone`). A decision is a **leaf**: it never points at
a task or a milestone. Markdown links may run from a decision to a task, but no
field does, so a "task that ratified this decision" is always an *inbound*
`references:` edge and never a queryable one.

### Identity rules

- **A milestone ID is not a version.** `m-4` is 0.6.0 and `m-5` is 0.5.0 — the
  IDs were allocated in planning order, not version order. Read the title, never
  infer the release from the number.
- **The file name is the record's display name, not its identity.** Renaming a
  task's title through the CLI does not rename its file; the `id:` field is the
  identity, so a mismatched file name is cosmetic (fix it with `mv`, as done for
  `TASK-25.1`).
- **Decision titles are prose and are not kebab-derived.** `decision list` prints
  the title, so the CLI and the file name drift harmlessly.
- **Documents number in creation order across both folders.** `doc-10` sits at the
  docs root while `doc-9` is under `plans/`; the ID is global, the folder is
  taxonomy.

## 2. Predicates: the one edge, and the two meanings it must not carry

`dependencies:` is the only task-to-task edge. It is a DAG (`backlog doctor` fails
on cycles) and it must mean exactly one thing:

> **A depends on B** = A may not be started to completion until B is closed.

It must **not** be used to mean "A is composed of B". Composition has its own
mechanism — a sub-task (`task create -p <parent>`) produces `TASK-N.M` with a
`parent_task_id` field, which is a distinct edge the graph can display and the
board can group by.

Why the distinction matters in practice: the v2 epic `TASK-38` is a *container*
whose whole purpose is composition, but the schema has no container class, so it
carries `dependencies` and its "what this is" meaning lives in prose. That is the
known cost of a two-class model and the reason containers are used sparingly.

Other edges, for completeness:

| Edge | Mechanism | Queryable |
| --- | --- | --- |
| task → milestone | `milestone:` field | yes |
| task → task (blocking) | `dependencies:` | yes |
| task → task (composition) | `parent_task_id:` via `-p` | yes |
| task → decision/doc/file | `references:` | yes, untyped |
| doc/decision → task | markdown link in body | no |
| git tag → release | repository tag | no |

## 3. Statuses

**Task statuses** are the configured three: `To Do` → `In Progress` → `Done`.
Ending work moves a task out of the board, so `Done` is the only exit.

**Decision statuses** are a second, independent lifecycle with no CLI enforcement:

> **`status:` tracks the decision, not the delivery.** Mark `accepted` when the
> *decision itself* is settled — meaning its Decision section describes what this
> project will do and no "remain proposed" clause inside it is still open. A
> closed implementation task is not sufficient, because tasks close on
> evidence for a slice while the decision covers the general rule.

Promotion is a **hand edit**: the CLI exposes only `decision create` and
`decision list`, so there is no `decision edit`. When editing one by hand:

1. Change only the `status:` line in the front matter; do not touch `date`.
2. Append a dated `## Status review (YYYY-MM-DD)` section recording the evidence
   that promoted it, or the condition that keeps it open.
3. Never delete existing sections. A decision's body is its history — several
   "Confirmed ..." sections already record amendments without status changes.

If a decision is only *partly* realized, keep it `proposed` and record the split
in its status review (see `decision-6`, `decision-12`, `decision-14`). Do not
invent a `partially accepted` value: the schema has two values and a dated section
carries the nuance honestly.

### Promotion audit (2026-10-24)

All 13 proposed decisions were checked. One is promotable and was promoted
(`decision-6`, once `TASK-25.1` and `TASK-25.2` supplied its two missing
boundaries); the other twelve each have an unmet condition, and most of those
conditions are already a backlog task:

| Decision | Subject | Unmet condition / blocking task |
| --- | --- | --- |
| decision-4 | async-first networking transport | TASK-5 (m-1) |
| ~~decision-6~~ | models/services/core/adapters separation | **accepted 2026-10-24** — `testing` and `adapters/qgis` landed |
| decision-7 | layered pytest fixtures, properties, BDD | TASK-7 (m-2) |
| decision-8 | separate check/test/dev/build workflows | TASK-16 (check), TASK-26 (test/dev) |
| decision-9 | allowlisted typed bridge endpoints | TASK-4 (m-2) |
| decision-10 | dataclass authoring + schema-driven TS generation | TASK-17; its own closeout says so |
| decision-11 | one context-injected class per algorithm | class-per-algorithm and provider registration landed (TASK-14, TASK-39); open on `QgsProcessingAlgorithm`/`createInstance` phases, mid-flight cancellation and a thread-affinity proof |
| decision-12 | one context-injected controller per surface | TASK-3 (m-1) |
| decision-13 | runtime-bound local jobs | TASK-15 (m-1) |
| decision-14 | QGIS-free import rules in `check` | TASK-16 (m-3); `QGIS001`/`ARCH001` do not exist |
| decision-15 | refresh through owned runtime generations | TASK-21 (m-3) |
| decision-16 | reusable layer styles vs UI themes | layer-style half landed (TASK-25.4); open on the `ctx.styles`/`ctx.ui.theme` surface it defers |
| decision-23 | Tauri-inspired QWebChannel patterns | TASK-4 (m-2) |

Two decisions have no inbound reference anywhere: `decision-5` (Rust algorithms
post-v1) and `decision-9` (typed bridge endpoints). That is acceptable for
direction-only records; do not create a task merely to reference them.

**Re-audit trigger:** a decision whose blocking task closes should be re-read in
the same session, because that is exactly when its status drifts.

## 4. Work item types

Configured types are `bug, feature, enhancement, task, chore, docs, spike`; this
board uses three — `feature`, `chore`, `spike` — and every task has one.

- **`feature`** — user-visible capability or a service contract.
- **`chore`** — release gates, qualification evidence, tooling and refactors that
  produce no new capability. **Evidence-only work is a chore, not a feature.**
- **`spike`** — a question to answer with a recorded recommendation, whose closeout
  names its blockers.

Rules for the unused four, so that "the board has no bug type" never becomes
"bugs are not tracked":

- **`bug` may be created without a milestone**, and must carry a reproducing
  failure — a failing test, a command with its output, or a recorded environment.
  A suspicion is a spike, not a bug. Do not open a bug to represent a known
  limitation that a qualification task already records.
- **`enhancement` is not used here.** It would duplicate `feature`; pick `feature`.
- **`docs`** is for documentation work that is not an acceptance criterion of
  another task — for example writing migration notes for a *landed* 0.x breaking
  change. Do not pre-create it for notes that no change yet requires.
- **`task`** is a fallback; prefer one of the three named types.

## 5. Slicing

Slice a task when it spans more than one seam or reviews as more than one unit —
roughly, **more than ~3 acceptance criteria that cannot be proven by one change
set**. Do not slice to make a board look populated, and never slice a task that is
already scheduled for the same sprint into smaller tasks whose only difference is
sequencing.

Rules:

1. **Slice under the task, not under the epic.** `task create -p TASK-N` gives
   `TASK-N.M`. Slicing a feature under a container would duplicate the feature.
2. **The parent keeps the criteria.** Sub-tasks carry the executable, verifiable
   criteria; the parent's criteria are checked only when the slices are closed.
   Record the decomposition in the parent's notes with the dependency shape.
3. **Declare the real order.** Parallel slices get no dependency on each other;
   only genuine blocking edges become `dependencies`.
4. **Sub-tasks do not inherit the milestone.** They must be assigned explicitly
   (`-m`), and they inherit neither `priority` nor `type`.
5. **A slice that produces only evidence is a `chore`** and should be closed by
   quoting the run, not by asserting success.

Current example: `TASK-25` is sliced into `TASK-25.1`–`TASK-25.5` (contracts and
fakes; native layer/project adapter; settings and notifications; packaged QML;
real-host qualification).

## 6. State that is not a field

Some concepts have no class, and inventing a field for them is worse than a
document:

- **Sprint / iteration** — lives in a plan document (`doc-9` for v2) and in the
  milestone body. Per-task sprint fields cost 25 edits a sprint and are not
  queryable by anything this project runs.
- **Blocker** — a task stays in its status and its blocker is named in a comment
  with a date and a reason, as the GitHub Actions outage was recorded (`doc-8`).
  Do not create a "blocked" status or a blocker task.
- **Release identity** — git tags, not task fields.

## 7. Evidence discipline

- A checked box means **proven**, not intended. Unproven criteria stay open with
  the missing evidence named.
- Tests are the default evidence; a real QGIS host test is required wherever the
  criteria concern native behaviour. The opt-in harnesses are the mechanism
  (`QGIS_SDK_*` flags, harnesses in `packages/qgis-sdk/scripts`, QGIS-free tests
  in `packages/qgis-sdk/tests/scripts`).
- The Linux sandbox is headless: no GUI, canvas, 3D or Windows/macOS claim may
  originate from it, and the recorded evidence must say so. TASK-33 owns those.
- Notes record execution progress; comments record review discussion and blockers.
- Never restate a CI result that was not observed.

## 8. CLI notes

- Always non-interactive when driven by an agent: `--plain` for reads, `--json` for
  parsing. Avoid bare `board`, `browser` and task-detail views.
- Run through `pixi run -e bun bunx backlog.md <command>`. The workspace pins
  `backlog.md` `^1.53.0` as a root dependency and resolves 1.53.0 from
  `node_modules`. Install the locked workspace first
  (`pixi run -e bun bun install --frozen-lockfile`): without it, `bunx` silently
  downloads the newest release instead — 1.55.3 was observed that way, and a
  different CLI version can write different front matter.
- `task edit -t` does not rename the file; `decision` has no `edit` subcommand;
  sub-task IDs are `TASK-N.M` and must be passed as such to `--dep`.
- `backlog doctor` fails on cycles and duplicate IDs — run it after bulk edits.

## 9. Related

- [doc-4](../docs/plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md) — version policy and the task inventory.
- [doc-9](../docs/plans/doc-9%20-%20V2-sprint-train-and-0.2.0-dependency-order.md) — the v2 sprint train.
- [TASK-38](../tasks/task-38%20-%20Epic-v2-0.2.0-native-runtime-and-Processing-algorithms.md) — the container that exercises the composition rule.
