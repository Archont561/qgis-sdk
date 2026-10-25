---
id: TASK-53
title: >-
  Offer the curated services on PluginContext and build the web-view surface
  from it
status: In Progress
assignee:
  - '@agent'
created_date: '2026-10-25T09:59:00Z'
updated_date: '2026-10-25T09:59:00Z'
labels: []
milestone: m-3
dependencies: []
type: feature
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Put layers, project, settings, styles, algorithms and workers on PluginContext as optional fields with require_<name>() accessors; add HostServices.from_context(ctx) so the bridge wraps the same instances a Python handler uses; add qgis_sdk.adapters.qgis.native_plugin_context to assemble every PyQGIS adapter on one scope; make the scaffold use it inside QGIS. decision-32.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 PluginContext exposes the six services optionally; require_<name>() refuses by capability name and on a closed scope
- [ ] #2 HostServices.from_context shares instances with the context and defaults network.fetch to the client's transport
- [ ] #3 native_plugin_context wires every native adapter on one scope; scaffold build_context uses it when a QgsApplication runs and stays importable without QGIS
- [ ] #4 doc-12 and decision-32 recorded; task in the doc-4 0.4.0 inventory; pure suite, native services suite and scaffold qualification pass
<!-- AC:END -->
