---
id: TASK-66
title: Generate the typed bridge schema module and add QgisSdk.fromBridgeSchema
status: To Do
assignee: []
created_date: '2026-10-26T08:41:00Z'
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
- [ ] #1 bridge generate --check and the CI drift check work on bridge.schema.ts; the generated module has no validators and imports only defineBridgeSchema; the pure generator tests and the example's bindings script pass.
- [ ] #2 QgisSdk.fromBridgeSchema(schema) is typed from the generated Operations/Streams: a wrong argument shape or an unknown operation is a tsc error (type-level test), and at runtime an argument or a reply outside the schema raises QgisSdkContractError with code contract_validation_failed; bun tests cover primitives, list/tuple, union, Literal and nested dataclass schemas.
- [ ] #3 A page is three statements (import QgisSdk, import the schema, fromBridgeSchema) with the default QWebChannel transport; the React BridgeProvider and useOperation work on the instance; the testing host scripts from the schema; the TS suite, typecheck and Biome are green.
- [ ] #4 doc-13 documents QgisSdk, the schema module and the 0.4.0 migration (before/after main.ts); TASK-60 and m-5 record QgisSdk in the bridge 0.4.0 delta; the scaffold templates switch under TASK-65 at the ts-v0.4.0 stamp per decision-41.
<!-- AC:END -->
