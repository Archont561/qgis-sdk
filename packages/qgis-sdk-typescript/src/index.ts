/**
 * The root entry of `@archont561/qgis-sdk`: everything a page needs to talk to
 * a QGIS host in one import.
 *
 * - `QgisSdk` (`./qgis-sdk`), the object a page builds from its generated
 *   `bridge.schema.ts` with `QgisSdk.fromBridgeSchema(schema)`, plus the schema
 *   definition (`./schema`) that module calls and the validator
 *   (`./validate`) the SDK checks every message with;
 * - the error root and the version 1 plugin-description contract
 *   (`./declarations`), mirroring the QGIS-free `qgis_sdk.models` and
 *   `qgis_sdk.declarations`;
 * - the transport client (`./bridge`), also reachable as
 *   `@archont561/qgis-sdk/bridge`, and the default QWebChannel transport
 *   (`./webchannel`) `QgisSdk` connects through when given no other.
 *
 * The host namespaces also come as `qgis.host` on a `QgisSdk`; their own entry
 * point (`./host`) stays for a page that holds a bare `BridgeClient`. The React
 * bindings (`./react`) and the scripted harness (`./testing`) stay behind their
 * own entry points: one needs an optional peer, the other is a development
 * dependency. Importing this module touches no browser or Qt global; only
 * `createWebChannelTransport`, when called, reads `window.qt`.
 */

export * from "./bridge";
export * from "./declarations";
export * from "./errors";
export * from "./qgis-sdk";
export * from "./schema";
export * from "./validate";
export * from "./webchannel";
