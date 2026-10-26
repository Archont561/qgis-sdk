/**
 * The root entry of `@archont561/qgis-sdk`: everything a page needs to talk to
 * a QGIS host in one import.
 *
 * - the error root and the version 1 plugin-description contract
 *   (`./declarations`), mirroring the QGIS-free `qgis_sdk.models` and
 *   `qgis_sdk.declarations`;
 * - the transport client (`./bridge`), also reachable as
 *   `@archont561/qgis-sdk/bridge`.
 *
 * The generated host namespaces (`./host`), the React bindings (`./react`) and
 * the scripted harness (`./testing`) stay behind their own entry points: the
 * first is large and opt-in, the second needs an optional peer, the third is a
 * development dependency. None of this module imports a browser or Qt global.
 */

export * from "./bridge";
export * from "./declarations";
export * from "./errors";
