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
