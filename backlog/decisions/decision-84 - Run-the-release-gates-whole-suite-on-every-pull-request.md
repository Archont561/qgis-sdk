---
id: decision-84
title: Run the release gate's whole suite on every pull request, and stop simulating a missing QGIS with a name
date: '2026-11-13'
status: accepted
---
## Context

`autorelease` runs a pre-release quality gate before it cuts a tag. For a
`python`-scope release it runs four commands: `lint_python`, `format_check`,
`test_scripts` and `test_python` - the last of which is the **whole** suite,
`packages/qgis-sdk-python/tests`, in **one** process, with no per-row flags.

Every pull-request job ran something else. `Linux coverage` ran
`-m "pure and not smoke"`, `Linux checks` ran
`-m "native and not smoke"` with `QT_QPA_PLATFORM=offscreen` and
`QGIS_SDK_NATIVE_SERVICES=1`, and `cross-platform` ran the whole directory on
hosts with no QGIS at all. So the exact command the release depends on was
executed for the first time on `main`, after review, where a failure blocks a
release and no pull request can reproduce it.

It failed on 2026-11-12, twice: on `fe0a0b9` (PR #214) and on `b1afbeb`
(PR #215). The run said only "Process completed with exit code 1" at step 8;
job logs were not readable from the environment that had to diagnose it, and
the check-run carried no output. Reproducing the command on a throwaway branch
and publishing its output as a check-run summary found three failures:

```
FAILED tests/test_desktop_host.py::test_host_returns_a_class_factory_that_runs_the_plugin_without_qgis
FAILED tests/test_desktop_host.py::test_a_bare_interpreter_places_no_binding_and_refuses_ui_by_name
FAILED tests/test_ui_components.py::test_mounting_without_qgis_is_refused_by_name
3 failed, 3698 passed, 101 skipped, 7 deselected in 165.51s
```

Both are the same defect: a test that *simulates* a machine without QGIS, in a
process where QGIS is running. Each passed in the lane that ran it and failed
only when both halves shared an interpreter.

- **`test_desktop_host.py` patched a re-export.** Its `bare_interpreter`
  fixture did `monkeypatch.setattr("qgis_sdk.adapters.desktop.qgis_is_running",
  ...)`. That name worked while `desktop.py` was one module. PR #214 split it
  into `desktop/{__init__,_host,_lifecycle}.py`, and the package `__init__`
  re-exports the function with `from ._lifecycle import qgis_is_running` - a
  second name bound to the same object. `default_context` and
  `desktop_surfaces` call the one in `_lifecycle`, so the fixture pinned
  nothing; the host saw the running `QgsApplication` and built the native
  context and the surface host. In the pure lane nothing had started QGIS yet,
  so the patch was irrelevant and the test passed for the wrong reason.
- **`test_ui_components.py` cleared a package's own entry.** It dropped
  `qgis_sdk.adapters.qgis.components` from `sys.modules` and set the Qt names
  to `None`, expecting the re-import to fail. Once the catalogue is a package,
  its `._widgets` submodule stays cached, so the re-import reused it, never
  touched Qt again, and the mount succeeded.

## Decision

1. **The gate's command runs on every pull request.** `ci.yml` gains a job of
   its own, `Both layers in one process`, which runs
   `pixi run -e default automation -- test_python` - the release gate's exact
   command, without the native-services flag - and `checks` requires it next to
   `fast`, `linux`, `coverage` and `lts`. It is a job rather than a step in
   `Linux checks` so the cost is a runner-minute in parallel instead of three
   minutes on the required critical path.
2. **`tests/scripts/test_ci.py` holds the invariant, not the comment.** A new
   test reads the `Run quality gate` step from `autorelease.yml` and asserts
   every `automation -- <task>` it names is also named by `ci.yml` (with
   `check`'s composed tasks read from `dodo.py`). The one exception, `test_js`,
   is asserted to run on a pull request as the `bun test` command
   `cross-platform` uses. On the tree that failed this test reports
   `the release gate runs tasks no pull request runs: ['test_python']`.
3. **A simulated missing dependency patches the binding its caller reads.**
   `test_desktop_host.py` patches `qgis_sdk.adapters.desktop._lifecycle`, the
   module that defines `qgis_is_running` and the two callers of it, and asserts
   the pin took effect - so a future move of the function fails here, in every
   lane, instead of on `main`. `test_ui_components.py` purges the catalogue
   package and everything under it.

## Consequences

- A gate that is red on `main` can now be reproduced by running the same job on
  the pull request that would have caused it. The release train no longer
  discovers order-dependent tests first.
- Every pull request pays about three runner-minutes for the new row. The
  alternative - trusting two lanes that never share an interpreter - was
  already false twice in one day.
- `monkeypatch.setattr("pkg.name")` on a re-export is now a known trap rather
  than an accident waiting for a refactor: the suite's combined run is what
  catches the next one, because a patch that binds nothing only fails once the
  state it was meant to simulate is already true.
- `test_python` stays in the release gate. It is no longer a command with no
  pull-request twin, which was the whole problem.
