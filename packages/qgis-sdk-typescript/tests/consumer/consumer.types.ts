/**
 * The package as a consumer sees it: the built `dist/*.d.ts`, not `src`.
 *
 * `tsc -p tsconfig.dist.json` compiles this file after every build. It exists
 * because the declaration bundler has twice produced output that `src` never
 * showed: a `const` dropped for sharing its name with a type, and a class
 * duplicated per entry point so that a `QgisSdk` from the root was not
 * assignable to the `qgis` prop of `./react`. Each line here is one thing a
 * scaffolded page does across entry points.
 */

import { createElement } from "react";
import {
	type BridgeSchema,
	defineBridgeSchema,
	QgisSdk,
} from "../../dist/index";
import { BridgeProvider, useOperation, useQgisSdk } from "../../dist/react";
import { createBridgeHarness } from "../../dist/testing";

interface Operations {
	readonly ping: {
		readonly request: { readonly value: number };
		readonly result: number;
	};
	readonly "tools.reset": {
		readonly request: Record<never, never>;
		readonly result: null;
	};
}
type Streams = Record<never, never>;

const schema: BridgeSchema<Operations, Streams> = defineBridgeSchema<
	Operations,
	Streams
>({
	schema_version: 1,
	id: "demo",
	title: "Demo",
	actions: [],
});

// The root value and type share the name, through the bundler.
const harness = createBridgeHarness(schema);
const qgis: QgisSdk<Operations, Streams> = QgisSdk.fromBridgeSchema(schema, {
	transport: harness,
});

// A root instance is accepted by the React entry point.
void createElement(BridgeProvider, { qgis }, null);

// Methods nest by the dots in the id and keep their declared signatures.
const pinged: Promise<number> = qgis.ping({ value: 1 });
void pinged;
void qgis.tools.reset();
harness.expectInvoke("ping", (payload) => payload.value * 2);

// The testing entry point's harness is typed by the root's schema type.
function View(): null {
	const sdk = useQgisSdk<Operations, Streams>();
	const [, run] = useOperation(sdk.ping);
	void run({ value: 2 });
	return null;
}
void View;
