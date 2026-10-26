/** biome-ignore-all lint/correctness/useHookAtTopLevel: Vue composables share React's `use` prefix and are called from `setup()`, not from a React component. */
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
	type FormState,
	formStore,
	type HostQueryState,
	layersQuery,
	type OperationState,
	OperationStore,
	QgisSdk,
} from "../../dist/index";
import {
	BridgeProvider,
	useForm,
	useHostQuery,
	useOperation,
	useQgisSdk,
} from "../../dist/react";
import {
	getQgisSdk,
	setQgisSdk,
	form as svelteForm,
	operation as svelteOperation,
	toRune,
} from "../../dist/svelte";
import { createBridgeHarness } from "../../dist/testing";
import {
	provideQgisSdk,
	useForm as useVueForm,
	useOperation as useVueOperation,
	useQgisSdk as useVueQgisSdk,
} from "../../dist/vue";

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
	// A form is typed by the action id: the request names the fields the
	// values hold, the result types the submission.
	const [formState, form] = useForm(sdk, "ping", { initial: { value: 1 } });
	const submission: OperationState<number> = formState.submission;
	void submission;
	void form.submit().then((result: number | undefined) => result);
	const [layers] = useHostQuery(layersQuery(sdk));
	const refused: boolean = layers.status === "refused";
	void refused;
	return null;
}
void View;

// The same stores from the root, with no adapter: the vanilla path. A store
// built from the root is the one every adapter accepts.
const pingStore = new OperationStore(qgis.ping);
const state: OperationState<number> = pingStore.getSnapshot();
void state;
const vanillaForm = formStore(qgis, "tools.reset");
const vanillaState: FormState<null> = vanillaForm.getSnapshot();
void vanillaState;
const layerState: HostQueryState<unknown> = layersQuery(qgis).getSnapshot();
void layerState;

// The Vue entry point shares and reads the same instance.
function setup(): void {
	provideQgisSdk(qgis);
	const sdk = useVueQgisSdk<Operations, Streams>();
	const { run } = useVueOperation(sdk.ping);
	void run({ value: 3 });
	const { state } = useVueForm(sdk, "ping");
	const vueSubmission: OperationState<number> = state.value.submission;
	void vueSubmission;
}
void setup;

// The Svelte entry point: context helpers and the stores as Svelte stores.
function svelteInit(): void {
	const shared = setQgisSdk(qgis);
	const sdk = getQgisSdk<Operations, Streams>();
	void shared.ping;
	const ping = svelteOperation(sdk.ping);
	const rune = toRune(ping);
	const current: OperationState<number> = rune.current;
	void current;
	const buffer = svelteForm(sdk, "ping");
	void buffer.fields;
}
void svelteInit;
