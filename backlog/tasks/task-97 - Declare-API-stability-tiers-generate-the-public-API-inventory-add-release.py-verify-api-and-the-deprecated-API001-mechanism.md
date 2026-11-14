---
id: TASK-97
title: >-
  Declare API stability tiers, generate the public API inventory, add release.py
  verify-api and the @deprecated / API001 mechanism
status: Done
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-95
type: enhancement
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-56 points 1-4. __stability__ on modules and @stable/@evolving marks; qgis-sdk api dump writing the public API (names, signatures, model fields, CLI, rule ids, host operations, catalogue) as JSON; release.py verify-api diffing against the last tag and classifying additive / deprecating / breaking with the SemVer consequence; @deprecated(since=, removal=, use=) in Python and JSDoc in TypeScript; check API001 for a deprecated use; doc-12 Stability section rendered from the inventory.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 api dump is deterministic and complete for every stable module, verify-api classifies a fixture rename as breaking and a fixture addition as additive, and the release gate refuses a breaking change without the required version bump (tests/scripts).
- [x] #2 A @deprecated symbol warns once, is reported by check as API001 with the replacement and removal version, and verify-api refuses its removal before the window closes (pure tests).
- [x] #3 doc-12 renders the tier table from the inventory and a tests/scripts check fails when they disagree; every stable module carries its mark.
<!-- AC:END -->

## Implementation Notes

### AC 1 - the inventory and the classifier

`qgis_sdk_tools.api` is the whole thing in one package: `inventory()` reads the
installed tree, `diff()` compares two documents, `verdict()` collapses the
changes to additive / deprecating / breaking, `consequence()` says what the
release version has to be and `refusals()` says when it cannot carry what
changed. `qgis-sdk api dump` writes the document, `release.py verify-api` and
the `release_verify_api` doit task diff two of them.

Four judgement calls, recorded because each one decides what the freeze covers:

* **Which modules.** The 21 modules doc-12 documents as importable authoring
  surface, all of which import without QGIS - which is what lets the dump run on
  a plain runner. `qgis_sdk.adapters` and `qgis_sdk.bridge` are absent: listing
  them would promise that their shape survives a release.
* **`qgis_sdk.core` is listed although decision-56 calls `core/` internal.** The
  same point of the decision makes the context classes and service Protocols
  stable, and they are what `qgis_sdk.core` re-exports; the inventory reads only
  re-exported names, so the implementations under `core/` stay unpromised.
* **Default tier is `stable`** for every listed module, because nothing declares
  `__stability__` yet. AC 3 adds the per-module marks and narrows whatever turns
  out to be evolving; until then this document errs towards promising more,
  which is the direction a freeze should err in.
* **CLI entries include flags** (`check --json` is its own entry), because
  decision-56 freezes commands *and* flags: a dropped flag is then a breaking
  change on its own instead of hiding inside the command that kept its name.
  Duplicated `@app.command` registrations in `_commands/` collapse here because
  the typer app keys commands by name.

Model fields come along for free: a dataclass renders its fields in
`inspect.signature`, so `BufferRequest` is recorded as
`(layer_id: LayerInput, distance_metres: Metres, working_crs: CrsInput) -> None`
and a field rename is a signature change. Names that are not callables record
their type name, which is a weaker claim than a signature and the one place the
document is coarse.

Where it runs:

* `api/python.json` is tracked at the repository root and is the baseline every
  release is measured against.
* `ci.yml` runs `release_verify_api --check` in the required `Linux checks` job,
  so a pull request that changes the public API has to say so in that file and
  the change is reviewable in the diff.
* `release.yml` runs `release_verify_api --tag <previous python-v* tag>
  --version <release version>`, which is where the refusal fires. Before 1.0 a
  breaking change costs a documented minor, so nothing is refused today; after
  1.0 the same command refuses anything but `X.0.0`. Tags cut before this landed
  record no inventory, and the command says so rather than reporting the whole
  surface as new.

### AC 2 - the mark, the finding and the window

`qgis_sdk.deprecation` is the mark: `@deprecated(since=, removal=, use=)` attaches
a `Deprecation` record to the symbol, wraps a function or a class so the first
call (or first construction) in a process warns once, and leaves a constant
marked without wrapping it - the record is what the tooling reads, the warning is
for the person. Either way the sentence names the replacement and the version the
name disappears in.

The three readers share that one record:

* `qgis-sdk api dump` writes the marks into the document's `deprecations` list, so
  a mark is part of the contract rather than a comment.
* `check` reports an import of a marked name as `API001`, at warning severity -
  a deprecated name is not a broken build today, and a gate that failed on one
  would be switched off in the week it shipped. Both spellings are read:
  `from qgis_sdk.ui import OldPanel` and `models.Legacy` through
  `import qgis_sdk.models as models`. The table is read off the installed SDK, so
  a mark added in this release is visible to `check` in the same release.
* `release.py verify-api` refuses a removal that lands before `removal=`, using
  `early_removals()`: the version being cut is compared numerically against the
  announced one, so `1.10.0` is not read as older than `1.9.0`.

A new mark also classifies the release as `deprecating` rather than `additive`,
which is what makes the verdict useful: it says a window opened.

No production symbol carries a mark yet. Marking one is the deprecation sweep
(TASK-98), a decision about which names 1.0 drops - inventing one here to prove
the mechanism would be a promise nobody made. The mechanism is exercised by
`tests/scripts/test_api_deprecation.py`.

### AC 3 - the tiers, and one renderer

Every one of the 22 public modules declares `__stability__ = "stable"`, the
inventory records it, and `render_stability()` turns the record into the table
doc-12 carries between `<!-- stability:begin -->` and
`<!-- stability:end -->`. `qgis-sdk api stability` prints that table, which is
how the guide is updated - the same arrangement `qgis-sdk targets` has with the
support matrix, and for the same reason: a promise restated by hand drifts.

Three tests hold it: every public module declares a tier the vocabulary knows,
the inventory's tier is the module's declaration, and the guide's rendered block
equals a fresh render of the inventory. That third one is the disagreement check
AC 3 asks for - editing either side alone fails it.

All 22 are `stable` today. That is a claim, not a formality: `qgis_sdk.app`,
`server`, `console`, `environment` and `exports` are host-level surface a plugin
author imports, so 1.0 promises them too. If a future release wants one of them
to move faster, the mark changes here and the table changes with it.
