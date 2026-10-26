/**
 * The one error root of `@archont561/qgis-sdk`.
 *
 * Every error this package raises - transport, host contract, React binding,
 * test harness - extends `QgisSdkError`, so a page can catch the family in one
 * `instanceof` and switch on the stable wire `code` rather than on class names
 * or message text. The class lives in its own module so the entry points can
 * share it without importing each other.
 */

/**
 * Base class for expected SDK errors across the bridge boundary.
 */
export class QgisSdkError extends Error {
	public readonly code: string;

	public constructor(message: string, code: string = "sdk_error") {
		super(message);
		this.name = new.target.name;
		this.code = code;
	}
}
