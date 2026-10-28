---
id: decision-68
title: Explore additive plugin applications with explicit action groups
date: '2026-10-28 19:51'
status: proposed
---
## Context

The owner asked for a FastAPI-style authoring exploration for the next Python
release, including explicit action groups. Existing `@plugin` classes are
supported and must not be removed by this spike. A namespace alias alone does
not provide independent function registration or grouping. TASK-140's
[spike](../docs/plans/doc-30%20-%20TASK-140-plugin-application-and-action-groups-spike.md)
contains alternatives, a non-shipping class-lowering experiment, evidence and
qualification gaps.

## Proposed decision

**Superseded direction:** after this proposal, the owner requested replacing the
public class authoring API with applications, allowing private class lowering.
The migration is in progress and not release-ready; the additive compatibility
recommendation below is retained as historical spike context.

Prefer an **additive** explicitly owned application object with explicit action
group inclusion, if its API and qualification gates are approved. No implicit
module scanning or global current-plugin registry. Preserve original function
identity at decoration; inject a typed `PluginContext` by the host, outside the
request schema, with explicit fake contexts and eventually per-runtime overrides.
Use existing authorization, resource scopes and GUI-thread rules. Provide both
shared `describe(target)` and `target.describe()` with action bindings and UI
wires, without silently changing bridge serialization. Keep existing class-based
projects, imports and clients working. Do not depend on FastAPI or Pydantic.

The prototype lowers actions and streams to a temporary plugin class, experiments
with `module:app` resolution and unified describers, and has a narrow offscreen
QGIS host test with two apps and a fake Desktop interface. A separate opt-in
probe also used the real QGIS Desktop executable and iface offscreen, with two
temporary profile plugins, QGIS plugin-manager lifecycle and a source-edit reload.
This is not a choice of final architecture or a supported SDK API. Direct SDK app
discovery, bridge subscriptions, UI wire execution, visible GUI and packaged-ZIP
qualification, and cross-platform native coexistence remain qualification work.

## Consequences and gate

If approved, split implementation into registry/context, introspection and
schema, tooling/discovery, and native lifecycle qualification. Preserve and test
existing class paths; reject duplicates atomically; prove full equivalent bridge
schemas and generated clients or version the bridge explicitly. Update
TASK-78's 0.8.0 gate and migration notes based on measured results. The spike
itself neither implements a released API nor authorizes a version bump or
release. TASK-128 owns the proposed read-only expression context, and the
worker-first named-job refactor stays targeted to 0.9.0.
