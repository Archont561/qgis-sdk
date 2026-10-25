---
id: decision-37
title: State support as a matrix of demonstrated targets
date: '2026-10-25 20:05'
status: accepted
---
## Context

TASK-9 asks that the supported QGIS, Python, Qt and OS combinations be
explicit. Until now the promise was spread over prose: `requires-python
>=3.11` in three manifests, a per-requirement evidence table in doc-14, the
`cross-platform` job in `ci.yml`, task comments ("Linux with QGIS 4.1/4.2 and
CPython 3.11-3.14") and the headless harness reports. Nothing checked that
those statements agreed with each other or with the environment CI actually
runs, and a relock that moved QGIS or Qt would have changed the facts without
changing a word.

The evidence is also narrower than a version range suggests. One Linux host
(the locked Pixi environment: QGIS 4.2.3, Qt 6.11.2, Chromium 140, CPython
3.14) carries every native proof; the QGIS-free suite ran on CPython 3.11.2
and, through `pip`, on `windows-latest` and `macos-latest`; no Windows or macOS
QGIS installation has been seen (TASK-33). A claim like "QGIS 4.x on Python
3.11+" would promise combinations nobody ran.

## Decision

Support is stated as a matrix of targets, one row per OS, architecture,
interpreter series and QGIS series, each row either `qualified` with the
evidence that demonstrated it or `unqualified` with the blocker named. The
matrix lives once, as data, in `qgis_sdk_tools.targets.SUPPORT_MATRIX`;
everything else is derived from it:

- `qgis-sdk targets` prints it and says where the current host stands
  (information, exit code 0 either way; `--json` for machines);
- doc-12 carries the rendered table between markers, and a test fails when
  the two disagree;
- `tests/test_targets_native.py` reads the host the native suite runs on and
  requires it to be a qualified row, so a relock or a new candidate has to
  move the row in the same change;
- the release workflow records the table in its job summary next to the
  metadata and build checks, so a release says what it was qualified on.

Rows match on the series a user can read off an installation - QGIS `4.2`,
Qt `6.11`, Chromium `140`, Python `3.14` - not on a patch level, because the
patch is what the lock happens to carry, not what the kit depends on. A host
without QGIS is covered by the QGIS-free row for its interpreter, or by a row
that qualified the same interpreter with QGIS on top: the QGIS-free suite is
part of that evidence. A qualified row with QGIS names the Qt and Chromium it
was seen with; a different Qt or Chromium is a different target.

The matrix is a record, not a filter: `requires-python` stays `>=3.11`, the
scaffold's `qgisMinimumVersion` stays the plugin author's claim, and nothing
refuses to run on an unqualified host. The floor is what the packages
install on; the matrix is what the workspace proved.

## Consequences

- Adding a target means producing the evidence first (a harness run, a CI
  job) and then adding the row that cites it; TASK-33's Windows and macOS
  QGIS rows flip from `unqualified` to `qualified` the same way.
- Widening the Python series (3.12, 3.13) needs a run of at least the
  QGIS-free suite on that interpreter before a row may say so; the
  `cross-platform` job is where such a run belongs.
- A relock that moves QGIS, Qt or Chromium to a new series fails
  `test_targets_native.py` until the Linux row is updated, which is the
  intended friction: the support statement changes only when someone looks.
- Prose about support in READMEs, guides and task comments defers to the
  matrix; doc-14 keeps the per-requirement evidence behind each row.
