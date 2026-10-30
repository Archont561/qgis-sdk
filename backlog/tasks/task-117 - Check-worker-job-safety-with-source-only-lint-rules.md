---
id: TASK-117
title: Check worker-job safety with source-only lint rules
status: Done
assignee: []
created_date: '2026-10-28 14:47'
updated_date: '2026-10-30 16:57'
labels: []
milestone: m-8
dependencies:
  - TASK-115
  - TASK-116
type: enhancement
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Extend qgis-sdk check with job-specific source-only AST diagnostics for the 0.9.0 worker-first contract; coordinate with the named job declarations and restricted worker context in decision-65. This is early feedback, not proof of Python thread safety or a security sandbox.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Recognize @job and import aliases, inspect imports and direct API use inside jobs and module-level bindings referenced by jobs, and diagnose known GUI-thread-only Qt widgets, iface and live project access with actionable locations and guidance; tests cover aliases, shadowing and TYPE_CHECKING.
- [x] #2 Report unresolvable dynamic imports or indirect safety-sensitive usage conservatively where feasible; do not promise transitive analysis, and document helper, dynamic, alias and object-flow limitations. Avoid blanket bans on all qgis.core imports or all module imports; test valid worker-safe code to limit false positives.
- [x] #3 Exercise qgis-sdk check end-to-end on valid and unsafe named-job plugins with deterministic diagnostics and nonzero exit on errors; document configurable severity or strictness if offered, runtime guards, migration and the worker-safe patterns.
- [x] #4 A GUI-bound capability read from a thread other than the one its context was assembled on is reported once per capability and thread - a warning by default, a QgisSdkUnsupportedCapabilityError in developer mode - while headless and pure contexts are unaffected, proven by pure tests (decision-69 point 3).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ecosystem research: TASK-132 explores other QGIS and Qt diagnostics plus a rule catalog; worker-specific analysis remains in this task and must not claim thread-safety proof.

The runtime guard (decision-69 point 3) is the other half of the contract and belongs beside the rules: the lint reads what the source shows (including aliases, and where a helper is called from a job), the guard catches a capability captured on the driving thread and read on a worker, once per capability and thread, as a warning by default and a QgisSdkUnsupportedCapabilityError in developer mode. Neither proves thread safety; both limits are documented with the rules.

Delivered. Tools: qgis_sdk_tools/check/jobs.py adds JOB001 (a job body reaches GUI state: qgis.utils.iface - module-level or imported inside the body - a Qt/QGIS GUI class, QgsProject.instance(), or a module-level name holding one of those), JOB002 (a context attribute other than progress/cancellation, which a WorkerContext refuses by name) and JOB003 (warning: importlib.import_module/__import__ the check cannot follow), wired into check_project after check_source so qgis-sdk check and build reuse it. Jobs are recognised in all four spellings (job, qgis_sdk.job, an SDK alias, and @app.job on a module-level plugin instance), through import aliases; a name the body rebinds locally - a parameter, an assignment, an import inside the body - is resolved and not reported as the module binding, and a global declaration brings it back. Annotations, decorators and defaults are excluded because they run when the module is defined, not on the worker. Runtime: core/contexts.py records the thread that assembled a context and reports a GUI-bound capability (desktop, ui, layers, project, files, streams, actions) read from another thread once per capability and thread as QgisSdkThreadSafetyWarning, or as QgisSdkUnsupportedCapabilityError in a development session (QGIS_SDK_DEV_REQUEST), with a new models.QgisSdkThreadSafetyWarning in __all__ and GUI_BOUND_CAPABILITIES exported from qgis_sdk.core. Tests: tests/test_check_jobs.py (16) and tests/test_worker_guard.py (11). Docs: doc-12 gains a What may a job body touch? subsection, JOB001-JOB003 rows in the rule table and a migration bullet. Evidence: full suite 2281 passed, 59 skipped, 7 deselected in 143.77 s; ruff clean; alint 9/9; docs build + check-links 8020 links on 118 pages, 0 broken; bun test 42 pass. Not claimed: no transitive analysis (a helper the body calls is not followed), no object flow (a live layer passed in as an argument is invisible), a callable reached through JOB003 stays unknown, GUI_CLASSES is a curated list rather than every GUI-affine QGIS class, and the runtime guard is a report, not a sandbox.
<!-- SECTION:NOTES:END -->
