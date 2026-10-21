---
id: doc-6
title: TASK-13 Qt scheduler spike evidence
type: other
created_date: '2026-10-21 19:12'
updated_date: '2026-10-21 20:17'
---

# TASK-13 — Qt-compatible coroutine scheduling and safe cancellation evidence

**Status (2026-10-21):** the scheduling **seam** is proven on the Linux candidate
runtime and is worth keeping; the **public async authoring syntax** is still not
selected. This record states what was measured, what it does not cover, and the
scope-review trigger that ADR-22 requires. Nothing here qualifies a Desktop GUI
session, Windows or macOS; those remain TASK-33.

## The question this spike had to answer

[ADR-4](../../decisions/decision-4%20-%20QGIS-aware-networking-uses-an-async-first-transport.md)
records that "a coroutine/Promise is not evidence of non-blocking execution" and
requires the Qt scheduling integration and GUI-thread handoff to be defined before
async handler syntax is committed. [ADR-21](../../decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md)
requires bounded quiesce, refusal instead of forced replacement, and no killing of
workers. [ADR-22](../../decisions/decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md)
requires that a failed spike reopen the scope rather than silently downgrade the API.

So the spike had to answer one narrow question: **can SDK-owned coroutine work be
driven from the QGIS GUI thread such that the loop stays responsive, worker results
are delivered back on that thread, and cancellation/disposal are safe — and if not,
does the failure announce itself?**

## Mechanism under test

`qgis_sdk.core.scheduling` — a QGIS-free, thread-free `StepScheduler`:

- `submit(coroutine)` registers work and runs **no author code**; the host advances
  it with `tick()`, and each job may take at most `max_steps_per_job` (default 8)
  steps per tick, so one hot job cannot starve another.
- Two awaitables are understood: `Yield()` (return control to the host loop until
  the next tick) and `Handoff` (a `SimpleQueue` mailbox a worker fills).
  `Handoff.resolve()` / `fail()` are thread-safe because they only enqueue; the
  awaiting job resumes on the **driving** thread at its next step, never inside the
  worker's call. Awaiting anything else fails the job with
  `QgisSdkUnsupportedCapabilityError`.
- Cancellation is cooperative: a request is delivered as
  `QgisSdkJobCancelledError` at the job's next suspension point so author
  `finally` blocks run. **A job suspended on an unresolved `Handoff` is not
  interrupted**: it settles only once the worker acknowledges, because abandoning it
  would delete native resources under a running worker (ADR-21).
- `quiesce()` cancels everything, advances within a bounded tick window and returns
  `QuiesceOutcome(refused, blockers)` instead of raising: a refusal names the
  blocking job and the host keeps the current generation running.
- Disposal is the existing `ResourceScope`. `dispose()` detaches active jobs without
  resuming them and counts reports that arrive afterwards
  (`StepScheduler.dropped_reports`) rather than delivering them.

The scheduler is **not** yet wired into `PluginRuntime`, `JobContext` or the bridge;
that is TASK-15 work. No public API selection is claimed here.

## What the harness measures

`packages/qgis-sdk/tests/qualification/qt_scheduler_smoke.py` runs the scheduler
inside a real `QgsApplication` with a real `QTimer` heartbeat (2 ms interval), a real
`QThreadPool` worker and `processEvents()` driving the loop, across five phases:

1. **Control** — a 60 ms blocking handler on the GUI thread must starve the loop.
2. **Scheduled work** — the same 60 ms spent off-thread while the job awaits a
   `Handoff`; the loop must keep pace and the result must be delivered on the GUI
   thread, from a different worker thread id.
3. **Cooperative cancellation** — a worker polls `job.cancellation`, acknowledges,
   and only then does the author `except`/`finally` run.
4. **Late report after disposal** — the owning scope closes while a worker is in
   flight; its report must be counted as dropped and must not resume author code.
5. **Stuck work refuses replacement** — a worker that ignores cancellation makes
   `quiesce()` refuse and name the blocker; the job is left running, not disposed.

Responsiveness is judged against a 40 ms gap budget. Criteria come from
`decide_verdict`: any failing deciding criterion yields
`review-scope-before-async-syntax` and names the criterion.

### Results (three consecutive runs)

Environment: Linux 6.1.158+ x86_64 (glibc 2.36), Python 3.14.8, QGIS
4.2.3-Belém do Pará, Qt 6.11.2, `QT_QPA_PLATFORM=offscreen`, pool
`maxThreadCount = 2`.

| Run | Blocking-phase max gap | Scheduled-phase max gap | Scheduled gaps (mean) | Cancel ack | Late report dropped | Replacement refused | Verdict |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | 61.300 ms | 2.673 ms | 31 (2.001 ms) | yes | yes | yes | adopt-scheduler-seam |
| 2 | 61.407 ms | 2.596 ms | 31 (2.011 ms) | yes | yes | yes | adopt-scheduler-seam |
| 3 | 61.343 ms | 2.517 ms | 30 (2.028 ms) | yes | yes | yes | adopt-scheduler-seam |

Thread identity in all three runs: every delivery thread id equalled the GUI thread
id, and both workers ran on a single pool thread id distinct from the GUI thread (the
pool reused one thread; this does not establish concurrency limits). The refused
replacement reported `job 1 is waiting on an unresolved worker handoff`.

The pure part of the same semantics is pinned deterministically by 27 unit tests,
4 BDD scenarios and 2 Hypothesis properties (interleaved resolve/fail/cancel/tick/close
never resurrects a settled job and never delivers work after disposal), with 100 %
statement coverage of `core/scheduling.py` (303 statements).

## Behaviors the spike settled

- **Cooperative, never preemptive.** A cancellation request cannot settle a job whose
  worker has not acknowledged, so `quiesce()` refuses while that holds. This is the
  ADR-21 failure behavior, now expressed in code and tested.
- **Cancelling a queued job runs no author code.** The coroutine is closed
  unstarted, so an author `finally` cannot observe a half-started plugin.
- **A disposed owner is durable.** After `ResourceScope.close()`, `submit()` raises
  `QgisSdkScopeClosedError`, late worker reports are counted in
  `dropped_reports`, and the consumed `Handoff.owner` is cleared.
- **Refusal is a result, not an exception.** `QuiesceOutcome` lets an adapter report
  the blocker to the user instead of tearing down native state.
- **Fairness is bounded per job per tick**, which is what keeps a runaway generator
  from starving the GUI thread.

## The scope-review trigger fired, and was not papered over

The first harness run reported `passed = false` with
`verdict = review-scope-before-async-syntax` and
`scope_review_criteria = ["worker_acknowledged_cancellation"]`. Diagnosis: the harness
cancelled a job that was still `QUEUED` (it had never been ticked into suspension), so
by design no author code ran and no cancellation handler could have executed. The fix
was to the **harness sequence** — start the job into its suspension first — not to the
criterion, and not to a "less ambitious" API claim. A second real defect surfaced the
same way: phases 4 and 5 shared the scope disposed in phase 4, so the scheduler
correctly refused their submissions; each disposal-sensitive phase now owns its scope.
Both were found by running the harness rather than by reasoning about it.

## What this does NOT qualify

- **No display and no real `iface`.** The loop is driven by `processEvents()` with a
  bounded deadline, not by a QGIS Desktop session; no menu, dock, dialog or
  WebEngine view is involved. TASK-33 tracks the Desktop GUI, Windows and macOS
  targets, and coexistence with another plugin using the same optional native runtime.
- **Not a QGIS-networking result.** No `QNetworkAccessManager`, proxy, auth or TLS
  behavior was exercised, so ADR-4 remains proposed. The `Handoff` seam is the
  scheduling primitive an HTTP transport would use, not evidence that it works.
- **No timing or throughput claims.** The 2 ms heartbeat and 40 ms budget are
  thresholds for *this* sandbox on a 2-thread pool; nothing here measures maximum
  concurrency, scheduler overhead under load, or behavior on a contended machine.
- **Not a selected public API.** `StepScheduler` is currently internal; handler
  syntax, `JobContext` wiring, progress reporting and bridge event delivery are
  TASK-15/TASK-17 decisions informed by, not decided by, this evidence.
- The sandbox environment is an **unverified restore**: `pixi-sandbox` reported 9
  `dist-info/RECORD` integrity mismatches (`coverage`, `hypothesis`, `jsonschema`,
  `mako`, `pytest_bdd` in `build`/`default`) while all 603 transport blobs matched.
  Checks ran with `PIXI_FROZEN=true PIXI_NO_INSTALL=true`; no dependency or lockfile
  change was made. The root `build:conda` task still fails fetching conda-forge
  repodata in this sandbox, so no Conda package was built here; the PyPI wheel and
  sdist built and passed Twine.

## Consequences

- Keep the scheduler seam as the mechanism TASK-15 builds job ownership on; do not
  describe async handler syntax as proven until a real Desktop session and the
  Windows/macOS matrix reproduce these criteria (TASK-33).
- `ADR-4` stays **proposed**: the transport needs its own evidence on
  cancellation/timeout/limits, though the handoff and disposal rules it depends on are
  now specified and tested.
- Open items for the next decision: exact `max_steps_per_job` and quiesce window for
  a Desktop host, where settled jobs are pruned (this spike keeps only active jobs),
  progress-report throttling through the same seam, and whether a worker
  `Handoff` must carry an explicit acknowledgement token distinct from its result.

## Path update (2026-10-21)

Standalone developer scripts now live in their own directory rather than inside the
test tree, so the harness cited above is at
`packages/qgis-sdk/scripts/qt_scheduler_smoke.py` and its QGIS-free tests at
`packages/qgis-sdk/tests/scripts/test_qualification_scheduler.py`.
`packages/qgis-sdk/tests/qualification/` no longer exists; the same move applies to
`webengine_smoke.py`, `desktop_lifecycle_smoke.py`, `generate_contract.py` and
`generate_pydantic_contract.py`. The evidence here is otherwise unchanged: after the
move the harness re-ran on this host reporting `passed: true`,
`verdict: "adopt-scheduler-seam"`, blocking-phase max 61.412 ms against
scheduled-phase max 2.593 ms, and every generated contract schema stayed
byte-identical.
