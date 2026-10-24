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

## Status review, part 2 (2026-10-24): registration and the QGIS toolbox (TASK-39)

The earlier review called provider registration "not implemented, and not
claimed". TASK-39 implemented it, so that paragraph is superseded for the
catalog/provider part; the other gaps listed there (`QgsProcessingAlgorithm` /
`createInstance`, mid-flight cancellation, thread affinity) stand as written.

**What now exists.** `qgis_sdk.providers.Provider` is the registration object this
decision asked for, and it is the deliberate kind: not a shared mutable execution
object but a named collection whose algorithms are validated at registration and
described without construction. `@provider.algorithm` attaches the metadata,
refuses a duplicate id, refuses a class that is already declared elsewhere, and -
because it validates the whole request - refuses a class whose request has no
`run`, no representable schema, or a field a host cannot render. A refusal leaves
the class undeclared rather than half-declared.

**What registration buys.** `qgis_sdk.adapters.qgis.register_provider` turns a
`Provider` into a `QgsProcessingProvider` and each registration into a
`QgsProcessingAlgorithm`, so `provider:algorithm` appears in the Processing
toolbox, the modeler, batch mode and `processing.run`. Parameters come from the
request dataclass: `Annotated[str, LayerInput()]` is a vector-layer picker,
`Annotated[str, CrsInput()]` a CRS chooser, `Annotated[float, Metres()]` a
non-negative spin box labelled in metres, and plain `str`/`int`/`float`/`bool` map
to text/integer/double/boolean. Anything else is refused at registration.

**Consequences for this decision's open questions.** Algorithm ids are now scoped
to a provider (`reference:buffer`), so "algorithm IDs ... remain illustrative" is
settled: the local id follows the shared declaration grammar and the host composes
`provider:algorithm`. The bridge declares `FlagNoThreading`, which is the honest
position while the thread-affinity question is open, and it copies the produced
layer into the caller's sink instead of adding to the project - the SDK's
non-destructive output stays the SDK's, and the host owns the destination.

**Still open.** A provider does not register itself with QGIS: the plugin calls
`register_provider(...)` and keeps the returned bridge. Nothing here gives an
algorithm its own GUI beyond QGIS's generated dialog, and processing these on a
worker thread is still unqualified.
