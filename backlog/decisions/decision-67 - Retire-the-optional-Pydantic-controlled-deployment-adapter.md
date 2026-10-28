---
id: decision-67
title: Retire the optional Pydantic controlled deployment adapter
date: '2026-10-28 15:48'
status: accepted
---
## Context

The owner considers the optional Pydantic controlled-deployment prototype obsolete
and requested that SDK support be removed. The stdlib-only runtime already derives
and validates its own contracts; the prototype was not its default backend.

## Decision

Remove the SDK Pydantic adapter, its field helpers and the runtime and kit
`controlled-deployment` extras, along with prototype-specific tests, generators,
fixtures and qualification harnesses. Do not automatically install or depend on
Pydantic. Plugins remain free to use separately provisioned third-party packages;
this decision does not implement or prohibit future dependency-management work.

This amends the parts of decisions 6, 10, 14 and 35 that describe the optional
adapter as shipped. Historical qualification records describe what was tested
at the time, not current support. Since this removes public modules and extras,
it is a breaking Python change to ship in a future minor release with migration
notes, not a patch for an existing release. No release number is assigned here.

## Consequences

The retired adapter and its strict validation, JSON dispatch and field helpers have
no drop-in replacement in the SDK. Consumers must migrate to supported SDK
contracts or explicitly own and provision their own third-party integration. The
ordinary bridge contract, TypeScript schema examples and generic checks for
PEP 508 extras remain in place.

## Local implementation status (2026-10-28)

At the 2026-10-28 review, the active session branch contained uncommitted
implementation and local validation; at that point it was not merged, released
or CI-qualified; see [TASK-121](../tasks/task-121%20-%20Land-and-qualify-removal-of-the-Pydantic-controlled-deployment-adapter.md) for remaining landing and migration work.
