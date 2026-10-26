---
id: TASK-61
title: >-
  Make the bridge root entry the page import and prefix the generated contract
  errors
status: In Progress
assignee: []
created_date: '2026-10-26 06:56'
updated_date: '2026-10-26 06:57'
labels: []
milestone: m-5
dependencies:
  - TASK-58
priority: medium
type: enhancement
ordinal: 61000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Ergonomic refactor of @archont561/qgis-sdk recorded in decision-40. The root entry becomes a barrel over ./errors, ./declarations and ./bridge; isPlainRecord and the stream event kind list move to an unexported ./internal; the two never-raised mirrors of Python errors leave the root; StreamEventKind is declared once. The generator emits QgisSdkHostContractError (extends QgisSdkError, relative import of ./errors) for the host module and the import-free QgisSdkContractError (extends Error, code contract_validation_failed) for plugin clients; checked-in clients regenerated. What crosses QWebChannel is unchanged: BRIDGE_PROTOCOL_VERSION, PLUGIN_DESCRIPTION_SCHEMA_VERSION, HOST_SCHEMA_VERSION and HOST_FINGERPRINT all stay. Ships as bridge 0.4.0 paired with Python 0.6.0; stamping is TASK-60's.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 import { BridgeClient, QgisSdkError } from "@archont561/qgis-sdk" compiles and resolves the same bindings as ./bridge; a test pins the root export list to the union of ./errors, ./declarations and ./bridge and refuses isPlainRecord, STREAM_EVENT_KINDS, QgisSdkScopeClosedError and QgisSdkUnsupportedCapabilityError.
- [ ] #2 ./host exports QgisSdkHostContractError extending QgisSdkError with code contract_validation_failed; a regenerated plugin client exports QgisSdkContractError extending Error with the same code and no import line; generate_bridge_clients.py --check and the example's bindings check pass; HOST_FINGERPRINT is unchanged.
- [ ] #3 doc-13 Exports and 0.4.0 migration notes, doc-12 0.6.0 note, the package README and decision-40 describe the change; m-5, TASK-60 AC #5 and doc-4 record the paired bridge 0.4.0 release instead of a bystander bridge.
- [ ] #4 Bun tests, typecheck, Biome, the Python suite and tests/scripts are green on the merge commit; no manifest version is bumped and no tag is created by this task.
<!-- AC:END -->
