/**
 * Public entry point for the QGIS SDK bridge.
 *
 * The bridge has no executable API yet. The package exists as the npm publishing
 * target and as the consumer of the generated contract types (see
 * `tests/contracts.test.ts`), so the entry point is deliberately empty and
 * `tests/index.test.ts` fails as soon as an export appears without a decision.
 */
export {};
