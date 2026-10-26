---
id: TASK-66
title: Generate the typed bridge schema module and add QgisSdk.fromBridgeSchema
status: Done
assignee: []
created_date: '2026-10-26T08:41:00Z'
updated_date: '2026-10-26 13:47'
labels: []
milestone: m-5
dependencies:
  - TASK-61
type: enhancement
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-44. qgis-sdk bridge generate writes web/src/bridge.schema.ts: the request/result interfaces as today, an Operations and a Streams interface, and export default defineBridgeSchema<Operations, Streams>({...describe_plugin()...}) plus CONTRACT_FINGERPRINT; validators and createOperations are no longer generated. @archont561/qgis-sdk 0.4.0 gains in the root: QgisSdk.fromBridgeSchema(schema, options?) returning one typed method per action and one handle per stream over a BridgeClient (default transport: the QWebChannel WireTransport, so transport.ts leaves the scaffold), defineBridgeSchema/BridgeSchema, a generic validator for the decision-10 declaration subset, and QgisSdkContractError extending QgisSdkError. BridgeProvider accepts the QgisSdk instance; testing scripts a host from the schema. --out web/src/bridge.ts keeps working one minor with a deprecation note. Wire, contract and HOST_FINGERPRINT unchanged.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bridge generate --check and the CI drift check work on bridge.schema.ts; the generated module has no validators and imports only defineBridgeSchema; the pure generator tests and the example's bindings script pass.
- [x] #2 QgisSdk.fromBridgeSchema(schema) is typed from the generated Operations/Streams: a wrong argument shape or an unknown operation is a tsc error (type-level test), and at runtime an argument or a reply outside the schema raises QgisSdkContractError with code contract_validation_failed; bun tests cover primitives, list/tuple, union, Literal and nested dataclass schemas.
- [x] #3 A page is three statements (import QgisSdk, import the schema, fromBridgeSchema) with the default QWebChannel transport; the React BridgeProvider and useOperation work on the instance; the testing host scripts from the schema; the TS suite, typecheck and Biome are green.
- [x] #4 doc-13 documents QgisSdk, the schema module and the 0.4.0 migration (before/after main.ts); TASK-60 and m-5 record QgisSdk in the bridge 0.4.0 delta; the scaffold templates switch under TASK-65 at the ts-v0.4.0 stamp per decision-41.
- [x] #5 QgisSdk.fromBridgeSchema(...).host is the typed decision-27 surface (layers, project, settings, notifications, styles, files, network.fetch as a stream) built from the package's host manifest; qgis.host.granted lists the ids the handshake advertised; a call outside the grants surfaces the host's refusal; bun tests cover a full and a narrowed grant set.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on the sprint-2 branch (decision-44). Python: Dispatcher answers kind "handshake" (protocol, generation, plugin description, host ids the view may call; stale generation refused as before); generate_schema_typescript renders bridge.schema.ts (typed Operations/Streams, defineBridgeSchema default export, CONTRACT_FINGERPRINT; the only import is from the SDK root), bridge generate defaults to web/src/bridge.schema.ts and keeps --out web/src/bridge.ts rendering the 0.3.0 client with a deprecation note; generate_bridge_clients.py owns a third artifact (tests/contracts/generated/clients/sites.schema.ts) under the CI drift sweep, and CI runs the example's bridge generate --check. TypeScript: src/schema.ts (BridgeSchema, OperationsOf, StreamsOf, defineBridgeSchema), src/validate.ts (validateAgainstSchema, QgisSdkContractError code contract_validation_failed), src/webchannel.ts (insideQgis, createWebChannelTransport, QgisSdkWebChannelError code no_web_channel), src/qgis-sdk.ts (QgisSdk namespace + instance type; fromBridgeSchema with transport/client/timeoutMs/channelObject; schema, client, host with granted, ready, close; strict request / lenient result validation; stream handles validating declared event kinds). BridgeClient.handshake(); BridgeProvider accepts qgis, useQgisSdk; createBridgeHarness(schema, { granted }) answers the handshake from the schema. tests/schema.types.ts is the tsc-only type-level suite. Two bundler findings shaped the code: @bunup/dts drops a const that shares its name with a type alias, so QgisSdk is a namespace; a unique-symbol phantom key is duplicated per entry point by the dts bundler, so BridgeSchema's phantom is the string key "~types". Example: main.ts is three statements, app.ts takes the QgisSdk, app.test.ts runs on createBridgeHarness(schema), transport.ts and bridge.ts are gone; web/package.json's bindings script is one release ahead of the scaffold until TASK-65 (test_reference_example.py spells the exception out). doc-13 rewritten around the schema module with the 0.4.0 before/after main.ts; m-5, TASK-60 and doc-18 updated.

Merged #94 → 36175ff (CI green on checks, macOS, Windows). Validation on the merge: Python suite 1516 passed / 43 skipped, tests/scripts 241, QGIS_SDK_REFERENCE=1 harness 5 passed (handshake answered by the real dispatcher inside a QWebEngineView), bun test 231/0, typecheck, Biome, vitest 5, both generators --check up to date. Method shape and the scaffold templates were revised in the follow-up PR (decision-44 and decision-41 status reviews).
<!-- SECTION:NOTES:END -->
