---
id: decision-11
title: Use one context injected class per Processing algorithm
date: '2026-10-16 08:05'
status: proposed
---
## Context

Algorithms need declarative metadata, typed inputs/results and pure logic tests without mandatory QgsProcessingAlgorithm inheritance. An earlier grouped-method example was exploratory; the preferred direction is one class per algorithm.

## Decision

Proposed: one decorated plain class per algorithm, one typed `run(inputs) -> Result` entry point, optional private helpers and constructor-injected `self.ctx: AlgorithmContext`. Inspect the class without constructing it. Group classes through an explicitly registered provider/catalog, not a shared mutable execution object. Construct a fresh author instance and execution context for each invocation.

AlgorithmContext provides execution-safe services, cancellation, progress/feedback, temporary/output resource management and input resolution. It is not PluginContext: no implicit iface, dialogs or GUI notifications. Share narrow service contracts where safe. The QGIS adapter implements parameter/output conversion, validation, createInstance behavior and preparation/execution/post-processing phases. Distance units/reference layers, geometry constraints, CRS, feature sources and output destinations require explicit GIS semantics beyond ordinary str/float annotations. Respect native thread affinity; context injection does not make arbitrary native calls worker-safe. Finalize outputs and clean temporary resources on every outcome.

## Consequences

- Pure handler tests use fake AlgorithmContext; real Processing/provider/geometry behavior needs integration tests.
- Keep Python as the v1 execution implementation and optional native compute backend-neutral (ADR-5).
- Algorithm IDs, model constraints, provider registration and exact context signatures remain illustrative until implemented.

## Confirmed second-interview refinement (2026-10-16)

Reference behavior is constrained by [decision-19](decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md): non-destructive new outputs, GUI-thread project addition after success, explicit working CRS/units and cleanup on failure/cancellation. These are accepted policies; exact parameter types remain proposed.

## Status review (2026-10-24): what TASK-14 implemented of this decision

TASK-14 landed the authoring half of this decision. What is implemented is listed
first, but the gaps follow in the same section on purpose: this slice is not the
whole of the decision, and the unimplemented parts should not be read as done.

**Implemented**

- One decorated plain class per algorithm (`@algorithm`), with one typed
  `run(inputs) -> Result` entry point and a constructor-injected
  `self.ctx: AlgorithmContext`. `describe_algorithm` inspects the class without
  constructing it, and the request/result schemas come from the same
  `qgis_sdk.declarations` generator plugin actions use, so an algorithm's inputs
  are held to the documented typing subset.
- A **fresh author instance and a fresh `AlgorithmContext` per invocation**, over
  a child scope that `invoke` closes again. A second run cannot see the first
  run's context; `tests/test_algorithms.py` observes both facts rather than
  assuming them.
- The execution capability is `Algorithms` (a narrow service), not a universal
  context: `AlgorithmContext` gained exactly that one field and still has no
  `iface`, no dialogs and no GUI notifications.
- Explicit working CRS and units for the distance operation: `BufferRequest`
  requires `working_crs` and `distance_metres`; the native adapter refuses a
  geographic CRS or non-metre units instead of picking a projection. The
  centroid operation has no distance and needs neither, as decision-19 requires.
- Non-destructive outputs, cleanup on every outcome, and project addition only
  after success (`invoke`).

**Not implemented, and not claimed**

- **Registration through an explicit provider/catalog.** Classes are described
  and invoked directly; there is no catalog object yet. The decision text marks
  provider registration as illustrative, and TASK-14's criteria do not require
  it, so it stays open rather than half-built.
- **`QgsProcessingAlgorithm` / `createInstance`.** The reference operations drive
  QGIS's own native algorithms through `Algorithms.execute`; the author class is
  *not* registered as a QGIS provider algorithm, so Processing's own
  preparation/execution/post-processing phases, parameter widgets and
  `createInstance` behaviour are not exercised. The adapter implements the phases
  it does have (validate, reproject, execute, open output, clean up).
- **Mid-flight cancellation and feedback.** Cancellation is read at phase
  boundaries - before the operation, and again before the output reaches the
  project. Aborting a running native operation needs a `QgsProcessingFeedback`
  bridge whose behaviour has not been qualified headlessly, so it is not claimed.
- **Native thread affinity.** Nothing here demonstrates or enables calling these
  adapters from a worker thread.

Status stays `proposed`: what is missing is registration and native-phase
fidelity, not polish.
