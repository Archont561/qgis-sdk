---
id: TASK-13
title: Prove Qt compatible coroutine scheduling and safe cancellation
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-21 20:51'
labels: []
milestone: m-0
dependencies:
  - TASK-23
references:
  - >-
    backlog/decisions/decision-4 -
    QGIS-aware-networking-uses-an-async-first-transport.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
  - backlog/docs/plans/doc-6 - TASK-13-Qt-scheduler-spike-evidence.md
  - backlog/tasks/task-33 - Qualify-Windows-macOS-and-Desktop-QGIS-targets.md
priority: high
type: spike
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prove Qt compatible coroutine scheduling and safe cancellation. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Demonstrate sync/async GUI responsiveness and correct thread handoff on candidate target runtimes.
- [x] #2 Test cancellation, disposal, stuck work and late callbacks with reproducible results.
- [x] #3 A failed spike triggers explicit scope review rather than a silent API downgrade.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Bounded spike slice, evidence-first, no silent API downgrade (ADR-22). (1) QGIS-free deterministic StepScheduler in packages/qgis-sdk/src/qgis_sdk/core/scheduling.py that drives real Python coroutines one step per tick and understands four awaitables: Yield (return control for a tick), Handoff (worker completes into a GUI-thread queue), Cancellation request checked at every await, and BoundedStep/overrun detection for stuck work. Jobs own a CancellationToken satisfying the existing services.Cancellation protocol; disposal closes the existing ResourceScope so late handoffs are dropped, not executed (AC2, ADR-21). (2) quiesce() refuses in-process replacement while a job cannot reach a safe point, naming the blocker instead of killing a worker (AC2/ADR-21). (3) Opt-in real-Qt harness tests/qualification/qt_scheduler_smoke.py running inside a headless QgsApplication: measure GUI-thread timer gaps for a GUI-thread-blocking job versus an off-thread job, prove worker thread id differs and completion is delivered on the GUI thread id, prove cooperative cancellation of a long worker, prove late handoff after unload is dropped, and prove refused replacement for stuck work; emit machine-readable JSON plus an explicit verdict (AC1). (4) Evidence doc backlog/docs/plans/doc-6 records results, platform limits (Linux headless only; Windows/macOS/Desktop under TASK-33) and the scope-review trigger if any criterion fails (AC3). Pure tests are deterministic and reproducible; no timing assertions in the suite. No dependency or lockfile changes. Do not claim a Desktop or non-Linux qualification.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-21 session (TASK-13 spike implemented; no merge yet). Environment is an unverified restore: scripts/restore.sh matched all 603 transport blobs but the final tree check reported 9 dist-info/RECORD integrity mismatches (coverage, hypothesis, jsonschema, mako, pytest_bdd across build/default), so checks ran with PIXI_FROZEN=true PIXI_NO_INSTALL=true and bun install --frozen-lockfile (81 packages). No dependency or lockfile change.

Bounded slice implemented, evidence-first per ADR-22:
- qgis_sdk/core/scheduling.py: QGIS-free, thread-free StepScheduler. submit() runs no author code; the host drives tick() and each job may take at most max_steps_per_job (default 8) steps per tick, so a hot job cannot starve another. Two awaitables: Yield() (control back to the host loop for a tick) and Handoff (SimpleQueue mailbox; resolve/fail are thread-safe because they only enqueue, and the awaiting job resumes on the driving thread at its next step, never inside the worker call). Awaiting anything else fails the job with QgisSdkUnsupportedCapabilityError.
- Cancellation is cooperative: QgisSdkJobCancelledError is thrown at the job's next suspension point so author finally blocks run, and a job cancelled while still QUEUED closes the coroutine unstarted (no half-started cleanup). A job suspended on an UNRESOLVED handoff is NOT interrupted: it settles only when the worker acknowledges, which is what keeps native resources from being deleted under a running worker (ADR-21).
- quiesce() cancels, advances within a bounded tick window and returns QuiesceOutcome(refused, blockers) instead of raising, naming the blocking job; resume() reopens submissions. Disposal reuses ResourceScope: dispose() detaches active jobs without resuming them, submit() afterwards raises QgisSdkScopeClosedError, and reports arriving late are counted in dropped_reports rather than delivered. Handoff.owner is cleared when its job consumes the report.
- tests/qualification/qt_scheduler_smoke.py: opt-in real-Qt harness (QgsApplication + QTimer heartbeat + QThreadPool worker + processEvents) over five phases: blocking control, off-thread scheduled work, cooperative cancellation ack, late report after disposal, stuck work refusing replacement. decide_verdict() yields adopt-scheduler-seam or review-scope-before-async-syntax and names the failing criteria.
- New errors are prefixed and exported only in prefixed form: QgisSdkJobCancelledError, QgisSdkSchedulingBlockedError. The scheduler is NOT wired into PluginRuntime, JobContext or the bridge: no public async syntax is selected by this task.

Validation (exact commands, unverified restore): root tests pixi run -e bun bun run test = 297 passed / 3 skipped (bridge 90 pass). pixi run -e bun bun run coverage = 272 passed / 3 skipped, TOTAL 100.00% (765 statements; core/scheduling.py 303 at 100%), gate 90% reached. Scheduling tests: 27 unit + 4 BDD scenarios + 2 Hypothesis properties. Real-Qt evidence, 3 consecutive runs (Linux 6.1.158+ x86_64, Python 3.14.8, QGIS 4.2.3-Belém do Pará, Qt 6.11.2, offscreen, pool maxThreadCount 2): all passed with verdict adopt; blocking-phase max gap 61.300/61.407/61.343 ms versus scheduled-phase max gap 2.673/2.596/2.517 ms against a 40 ms budget; every delivery thread id equalled the GUI thread id; both workers ran on one pool thread distinct from the GUI thread; cancel-ack, late-report-dropped and refused-replacement all true, blocker reported as "job 1 is waiting on an unresolved worker handoff". Opt-in smokes also run green via pytest with QGIS_SDK_QT_SCHEDULER=1 and QGIS_SDK_HEADLESS_LIFECYCLE=1 (14 passed). ruff lint/format, Biome, bridge typecheck and git diff --check pass; PyPI wheel+sdist built and passed Twine. Root build:build:conda still fails fetching conda-forge repodata in this sandbox (network allowlist), so no Conda package was built here; unrelated to this change.

AC status: AC2 checked — cancellation, disposal, stuck work and late callbacks are pinned by deterministic pure tests and reproduced by real-Qt runs. AC3 checked — the trigger fired for real and was not papered over: the first harness run reported passed=false, verdict review-scope-before-async-syntax, scope_review_criteria=["worker_acknowledged_cancellation"] because the harness cancelled a still-QUEUED job (by design no author code ran). The harness sequence was fixed, not the criterion, and no API downgrade was claimed. A second real defect surfaced the same way: phases 4/5 shared the scope disposed in phase 4, so the scheduler correctly refused their submissions; each disposal-sensitive phase now owns its scope.

AC1 left OPEN deliberately: "candidate target runtimes" is plural, and this evidence covers only Linux headless with processEvents-driven delivery, no display and no real iface. A real QGIS Desktop GUI session, Windows and macOS are TASK-33 and are not claimed here; the same standard that kept TASK-24 AC3 open applies. ADR-4 stays proposed (no QNetworkAccessManager/proxy/auth evidence). Evidence recorded in backlog/docs/plans/doc-6 - TASK-13-Qt-scheduler-spike-evidence.md, referenced from this task. Task stays In Progress pending AC1.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 20:17
---
Paths after the developer-script move (2026-10-21): the standalone harnesses and contract generators live in `packages/qgis-sdk/scripts/` and their QGIS-free tests in `packages/qgis-sdk/tests/scripts/`; `packages/qgis-sdk/tests/qualification/` is gone, so every earlier `packages/qgis-sdk/tests/qualification/...` reference in the notes of TASK-13, TASK-23, TASK-33 and doc-6 is superseded by the `scripts/` equivalent. Verified after the move: 297 passed / 3 skipped, coverage 100.00%, Ruff and format checks clean, generated contract schemas byte-identical, and the opt-in harnesses still pass when run directly.
---

created: 2026-10-21 20:45
---
Scheduling correctness follow-ups implemented (2026-10-21), uncommitted on this branch. (1) Control flow that is not an `Exception` (`KeyboardInterrupt`, `SystemExit`, or any host-defined `BaseException`) raised through author code is no longer absorbed as a quiet job failure: the job records it and the scheduler re-raises it to whoever is driving the tick, and the settled job is pruned from the active set as the exception unwinds so `drain()` cannot loop over a job that never advances again. (2) Disposal is final: a job disposal settled is never resumed later in the same tick (previously a still-queued neighbour was stepped after its coroutine had been closed and surfaced `RuntimeError: cannot reuse already awaited coroutine` at `steps: 1`), author code already on the stack cannot un-settle it by yielding, returning or raising, and an abandoned job always carries `QgisSdkScopeClosedError` as its reason even when its body never started. The abandoned started job's suspended frame is deliberately retained rather than closed - closing would run a pending `finally` against native objects that are already gone, which is what disposal exists to prevent - and that reasoning is now recorded in `Job._abandon`. Evidence: `packages/qgis-sdk/tests/test_scheduling.py` (35 tests) plus two new scenarios in `tests/features/step_scheduling.feature` (6); a mutation check confirmed each of the seven implementation pieces is a real discriminator (removing any one fails at least one test, and the removed pop-on-unwind guard hung an unbounded `drain()`, which is the hazard it prevents). Full suite 307 passed / 3 skipped, package coverage 100.00% over 780 statements, Ruff check and format clean, the same suite green on the declared floor Python 3.11.2 (282 passed / 3 skipped), and the opt-in real-Qt harnesses 23 passed with every flag set while `qt_scheduler_smoke.py` still reports `verdict: adopt-scheduler-seam` with all criteria true. Deliberately not changed: a re-entrant `tick()` from author code still lets the inner tick re-step the running job, failing it with `ValueError`; refusing nested ticks is a host-boundary decision for the TASK-15/ADR-4 transport seam, not a rule to slip into a bug fix.
---

created: 2026-10-21 20:51
---
Scheduling follow-up on this branch (2026-10-21): the two probe findings are closed in the working tree and re-verified against their original scenarios. (1) A host interrupt raised inside a job step now escapes tick() to the caller instead of being absorbed, while the job still records it as its error, and drain() then returns 0 - parametrised over KeyboardInterrupt, SystemExit and a private BaseException, plus a BDD scenario. (2) A job abandoned by disposal mid-tick is never re-driven, so no author code runs and no 'cannot reuse already awaited coroutine' escapes; _advance() checks settled/membership per step and prunes settled jobs in a finally so an unwinding interrupt cannot leave a settled job in the active set. core/scheduling.py is 318 statements at 100% covered, package suite 282 passed / 3 opt-in skips on CPython 3.14.8 and identically on 3.11.2. AC1 stays open: this is Linux only, and the real-Qt harnesses have only been run under 3.14.8.
---
<!-- COMMENTS:END -->
