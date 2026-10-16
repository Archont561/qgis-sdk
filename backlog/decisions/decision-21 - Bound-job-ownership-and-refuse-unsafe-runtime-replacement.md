---
id: decision-21
title: Bound job ownership and refuse unsafe runtime replacement
date: '2026-10-16 09:05'
status: accepted
---
## Context

Jobs outlive individual callbacks, cancellation is cooperative, and deleting old runtime resources while code still runs is unsafe. The initial reference slice does not need automatic retry orchestration.

## Decision

Jobs submitted from a view are view-owned by default. Disposing the view requests cancellation and immediately detaches its UI callbacks; hiding a dock is not disposal. Plugin-lifetime work is explicit and must not retain disposed view objects or callbacks. The host delivers completion on the GUI thread and prevents late callbacks into disposed owners. Exact late-subscriber behavior remains to be specified.

The initial job implementation includes submission, progress, results/errors, cancellation and ownership, but no automatic retries. Resubmission is explicit. A later retry policy requires classified failures, bounded attempts/backoff and idempotency/partial-side-effect semantics; an interrupted remote write must not be silently duplicated.

A cancellation request does not imply cancelled terminal state or safe teardown. During development reload, quiesce new calls and wait for acknowledgement/safe completion within a bounded policy. If work does not stop safely, refuse in-process replacement, identify the blocker and require explicit restart. Never kill a worker thread or delete native resources beneath it. Generation guards supplement, not replace, cleanup. Do not silently discard unsaved project state while restarting.

## Consequences

- Update the earlier Celery-inspired proposal (ADR-13): retries remain future design, not initial scope.
- Stateful tests cover disposal vs hiding, cancellation races, stuck work, plugin-owned jobs, old-generation callbacks and refused reload.
- Exact timeout, concurrency limits, scheduler and restart interaction require testing; this decision sets failure behavior, not arbitrary numeric values.
