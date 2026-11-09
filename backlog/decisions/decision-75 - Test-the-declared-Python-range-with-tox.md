---
id: decision-75
title: Test the declared Python range with tox
date: '2026-11-13'
status: accepted
---
## Context

All three distributions declare `requires-python = ">=3.11"`, and the workspace
never once ran on 3.11: the Pixi environments pin `python = "==3.14.8"`, the CI
matrix runs that environment, and the only other Python in the pipeline is the
`QGIS 3.44 LTS` row, which is about QGIS rather than about the interpreter. A
rule in `AGENTS.md` even says `qgis_sdk_tools.paths.walk_files` prunes the way
`os.walk` does "on the 3.11 this package still supports" - a claim about syntax,
typing and standard-library behaviour that nothing executed.

That is the shape of a support promise nobody can keep: the floor is normally
discovered by a user on a system Python, in the form of a package that installs
and then fails, or does not install at all.

## Decision

1. **tox names the range.** `tox.ini` carries one environment per minor version
   from the declared floor to the interpreter Pixi pins (`py311`-`py314`), and
   asserts nothing else: each environment installs the runtime and the tools
   from their source trees, the kit's `dev` extra, and runs the QGIS-free suite
   that already exists.
2. **A missing interpreter is a failure.** `skip_missing_interpreters = false`:
   a matrix that quietly drops a version proves nothing about that version, and
   a green run that tested three of four interpreters is the most expensive
   kind of false confidence.
3. **CI runs one job per version.** `.github/workflows/compat.yml` gives each
   version its own runner, installed by `actions/setup-python` and passed to
   `tox -e pyXY` explicitly. `tox-gh` would map the matrix for us; the mapping
   is four lines, and an extra dependency in the loop is an extra thing that can
   fail for a reason that is not about Python.
4. **tox stays outside Pixi.** The job exists to test the interpreter GitHub
   provides on a clean machine, not the one the lock pins. So `tox` comes from
   PyPI at an exact version in the workflow (`4.67.13`) and is documented as a
   local prerequisite, rather than being welded into the locked environments
   and thereby into the thing under test.
5. **The three copies of the range are held together by a test.**
   `tests/scripts/test_python_versions.py` reads the manifests' floor, the
   pinned interpreter, `tox.ini`'s envlist and the workflow matrix, and fails
   when one moves without the others.
6. **The suite is the QGIS-free one.** The compat matrix proves the packages
   import, install and behave on each interpreter; the native targets that need
   a QGIS build stay with the `QGIS 3.44 LTS` row, which is one QGIS and many
   interpreters' worth of work on its own.

## Consequences

- The floor is proven rather than declared: 2955 passed, 127 skipped, 7
  deselected on Python 3.11.2, from the same source tree the 3.14 environments
  run.
- Four more jobs per pull request that touches the packages, each about three
  minutes, running in parallel with the rest of the matrix.
- A new Python minor is two edits (an environment and a matrix entry) and the
  guard test says so when one is missing. Lowering the floor is the same edit in
  reverse; raising it means changing `requires-python` first.
- A dependency that only this gate uses is now versioned in two places - the
  workflow and the guide - because there is no lock entry to read it from. The
  alternative was adding tox to Pixi, which would have made the tool part of the
  environment it is meant to test.
