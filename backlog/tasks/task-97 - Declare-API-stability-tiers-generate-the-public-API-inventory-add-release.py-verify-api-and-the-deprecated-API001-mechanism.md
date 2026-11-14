---
id: TASK-97
title: >-
  Declare API stability tiers, generate the public API inventory, add release.py
  verify-api and the @deprecated / API001 mechanism
status: In Progress
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
- [ ] #2 A @deprecated symbol warns once, is reported by check as API001 with the replacement and removal version, and verify-api refuses its removal before the window closes (pure tests).
- [ ] #3 doc-12 renders the tier table from the inventory and a tests/scripts check fails when they disagree; every stable module carries its mark.
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

The `deprecating` verdict has no producer yet: the diff reads no deprecation
entries because `@deprecated` is AC 2's work. So are the removal window and its
refusal - "no earlier than the next major after 1.0 or the second following
minor before it" - which needs the `removal=` version the mark carries. AC 1
classifies what the document can currently describe; AC 2 fills in the rest.
