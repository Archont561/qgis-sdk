---
id: decision-34
title: Hand CLI commands a runtime through ctx.obj and library functions the same runtime as a parameter
date: '2026-10-25 12:30'
status: accepted
---
## Context

`qgis_sdk/__main__.py` is Typer over the public API: `new` and
`bridge generate` call library functions whose only effects are files and
stdout, so their tests run `CliRunner` against `tmp_path` and need nothing
injected. Milestone m-3 adds commands that are not like that: `check`
(TASK-16) reads a project and its configuration, `test` (TASK-26) selects a
runtime and spawns pytest, `dev` (TASK-6, TASK-21) holds a watcher and a
reconnecting bridge until interrupted, `build` (TASK-8) stages a temporary
tree and zips it. Each needs a working directory, an environment, output
streams, later a clock, a process runner and a QGIS probe, and some own
resources that must be released on every exit path. Testing them by
monkeypatching module globals is how CLI suites rot, and the owner asked on
2026-10-25 whether Typer's context could carry a lifetime API instead.

## Decision

1. **One runtime object, built once, passed everywhere.** `CliRuntime`
   (`qgis_sdk.cli`) is a frozen dataclass of concrete capabilities: `cwd`,
   `env`, `out`, `err` today; a command that needs a clock, a process
   runner or an environment probe adds a typed field, never a global.
   `CliRuntime.for_process()` is the real wiring and the only place that
   reads `os.environ`, `Path.cwd()` and `sys.std*`.
2. **The root callback seeds `ctx.obj` only when nobody did.** Typer's
   `ctx.obj` is the seam: the shell gets `for_process()`, a test passes
   `CliRunner().invoke(app, args, obj=fake)` and owns every effect the
   command can have. Commands read `ctx.obj` by attribute and treat it as
   data, not as a service locator.
3. **Library functions take the runtime as a parameter.** The rule from
   decision-8 and the module docstring stands: the CLI is argument parsing
   over the public API. `check_project(root, ...)` and its successors accept
   what they need as arguments, so a caller without a shell (build reusing
   check, a test, an editor integration) never goes through Click. `ctx.obj`
   exists for the CLI layer only.
4. **Resources the command opens close with the command.** Click's
   `ctx.with_resource()` / `ctx.call_on_close()` hold anything a command
   enters (a dev session, a staging directory) so it is released on success,
   error and `typer.Exit`. Long-running commands block inside the resource;
   Qt-originated failures are converted into a clean return before Click
   sees them, because an exception escaping a Qt slot aborts the process.
5. **Fakes live in `qgis_sdk.testing`.** `FakeCliRuntime` captures `out` and
   `err` in memory and takes `cwd` and `env` from the test; production code
   never imports it (the existing import-boundary test enforces this).
6. **Existing commands are not retrofitted.** `new` and `bridge generate`
   stay as they are until one of them needs something injectable; a pure
   function over `tmp_path` does not improve with a seam. `check` is the
   first consumer.

## Consequences

- Every m-3 command has the same three test layers: library tests on the
  functions, `CliRunner` tests with a fake runtime, and the opt-in
  real-QGIS smokes behind `QGIS_SDK_*=1`.
- `qgis_sdk.cli` is a pure layer at the scaffold rank in
  `tests/test_pure_imports.py`: stdlib and `models` only, no Typer import,
  so the runtime can be built in a subprocess that forbids native modules.
- `main()` stays a one-liner and the console-script and `-m` tests keep
  passing, because the real runtime is still the default.
- `FakeCliRuntime` is public API of the testing package and follows its
  compatibility rules.
