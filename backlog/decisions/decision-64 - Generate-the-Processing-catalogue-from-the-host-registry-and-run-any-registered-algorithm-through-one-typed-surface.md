---
id: decision-64
title: >-
  Generate the Processing catalogue from the host registry and run any
  registered algorithm through one typed surface
date: '2026-10-27 11:17'
status: accepted
---
## Context

`ctx.algorithms.execute()` accepts two hand-written requests, `BufferRequest`
and `CentroidRequest`, and the native adapter runs `native:buffer` and
`native:centroids` into new owned outputs (decision-19). That proved the
non-destructive shape; it does not scale to the roughly five hundred
algorithms QGIS 4 ships across `native`, `qgis`, `gdal`, `3d` and `pdal`,
nor to the providers a user installs (SAGA, GRASS, OTB), whose algorithms no
SDK release can know in advance. Writing a request class by hand per
algorithm is not an option; neither is an untyped `processing.run` string
with no description of what it takes and returns.

QGIS already describes every algorithm: `QgsApplication.processingRegistry()`
yields its parameters (type, label, description, default, options,
optional) and outputs (type, label). That registry is the one honest
source for the catalogue, and it is only readable inside QGIS.

## Decision

1. **One generic surface.** `ctx.algorithms` gains `list(provider=None)`,
   `describe(id)` and `run(id_or_request, params)`. `run` accepts any
   algorithm the host registry holds. Destination parameters the caller
   leaves out are allocated under the run directory and returned as owned
   layers, `FileRef`s or scalars; a caller may still name a destination.
   A failed run removes what it wrote before raising. Nothing is edited in
   place. Cancellation and progress are honoured at the boundaries the
   existing adapter honours; the SDK does not claim mid-flight abort of a
   native algorithm until that is qualified.
2. **The catalogue is generated, never written.** A runtime-side reader
   (`qgis_sdk.adapters.qgis.catalogue`) turns the registry into a plain
   `AlgorithmInfo` catalogue; pure emitters turn that catalogue into a
   Python module per provider (a `TypedDict` for the parameters, a request
   class per algorithm that validates before any data is read, and
   `REGISTRY`) and a TypeScript module (per-algorithm params and result
   types, an `AlgorithmRegistry` map). `qgis-sdk processing generate` runs
   the reader inside the project's QGIS install and writes both, with
   `--check` for drift, the way `bridge generate` does. The reader is the
   only piece that imports QGIS; the emitters are pure and tested over a
   fixture catalogue.
3. **The SDK ships a snapshot of the core providers.** `qgis_sdk.processing.
   {native,qgis,gdal,3d,pdal}` are generated from the pinned QGIS 4 by a
   repository script and drift-checked in CI, so an author has typing
   without running the generator, and the fake can answer `list` and
   `describe` offline. The snapshot is a convenience, not the contract: a
   host whose registry differs is described by `describe`, and a project
   generates what its own QGIS has.
4. **Two typed shapes in Python, one in TypeScript.** `native.Buffer(
   input=..., distance=...)` for readers of the hand-written predecessors,
   `run("native:buffer", {...})` typed by the `TypedDict` for readers of
   `processing.run`; both are the same generated data. TypeScript gets the
   `TypedDict` shape only, through `runAlgorithm(qgis, id, params)` typed
   by the generated `AlgorithmRegistry`.
5. **The bridge exposes it as curated host operations.** `algorithms.list`,
   `algorithms.describe` and `algorithms.run` behind the grants
   `algorithms.read` and `algorithms.run` (decision-27), one
   `HOST_FINGERPRINT` move. Generic JSON on the wire; the typing lives in the
   generated module next to the page.
6. **The fake runs nothing.** `FakeAlgorithms.list`/`describe` read the
   snapshot; `run` answers from outputs the test scripted and records the
   call, exactly like the bridge harness.

## Consequences

- Any installed provider is reachable the day it is installed; typing for it
  is one `qgis-sdk processing generate` away.
- `BufferRequest` and `CentroidRequest` stay as the hand-written predecessors
  of `native.Buffer` and `native.Centroids` and are documented as such; a
  later minor may retire them.
- The snapshot is large generated code; it lives under
  `qgis_sdk/processing/`, is excluded from lint like other generated
  artifacts, and is regenerated rather than edited.
- TASK-94 (m-10) shrinks to model files and batch runs. TASK-109 carries
  this decision in m-6 as sprint 5.
