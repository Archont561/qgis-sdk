/** {@link HostQueryStore}: reads of the curated host surface, refused before any call. */

import { QgisSdkBridgeAbortedError } from "../bridge";
import type {
	HostOperationId,
	LayerPage,
	VectorLayerInfo,
} from "../generated/host";
import type { QgisSdkCore, QgisSdkHost } from "../qgis-sdk";
import { asError, BaseStore } from "./base";

// ---------------------------------------------------------------------------
// HostQueryStore
// ---------------------------------------------------------------------------

/** Where one host query stands. */
export type HostQueryState<T> =
	| { readonly status: "idle" }
	| { readonly status: "loading" }
	| { readonly status: "ok"; readonly value: T }
	| { readonly status: "error"; readonly error: Error }
	| {
			/** The handshake did not grant `operation`; no call was made. */
			readonly status: "refused";
			readonly operation: HostOperationId;
			readonly message: string;
	  };

const IDLE_QUERY: HostQueryState<never> = Object.freeze({ status: "idle" });

/** What a host query runs once the grant is confirmed. */
export type HostQueryLoader<T> = (
	host: QgisSdkHost,
	options: { readonly signal: AbortSignal },
) => Promise<T>;

/**
 * Read the curated host surface, grant first.
 *
 * `refresh` waits for the handshake, then - when `qgis.host.granted` lacks
 * the operation the query needs - settles on `refused` without a call, so a
 * page can show "ask the plugin author for `layers.read`" instead of a
 * `not_authorized` fault. Otherwise the loader runs with latest-wins
 * semantics like an operation store.
 */
export class HostQueryStore<T> extends BaseStore<HostQueryState<T>> {
	private generation = 0;
	private controller: AbortController | null = null;

	public constructor(
		private readonly qgis: QgisSdkCore<unknown, unknown>,
		public readonly operation: HostOperationId,
		private readonly loader: HostQueryLoader<T>,
	) {
		super(IDLE_QUERY);
	}

	public readonly abort = (): void => {
		this.generation += 1;
		this.controller?.abort();
		this.controller = null;
	};

	public readonly reset = (): void => {
		this.abort();
		this.publish(IDLE_QUERY);
	};

	public readonly refresh = async (): Promise<T | undefined> => {
		this.abort();
		const mine = this.generation;
		const controller = new AbortController();
		this.controller = controller;
		this.publish({ status: "loading" });
		try {
			await this.qgis.ready;
			if (this.generation !== mine) {
				return undefined;
			}
			if (!this.qgis.host.granted.includes(this.operation)) {
				this.publish({
					status: "refused",
					operation: this.operation,
					message: `this view was not granted ${this.operation}`,
				});
				return undefined;
			}
			const value = await this.loader(this.qgis.host, {
				signal: controller.signal,
			});
			if (this.generation !== mine) {
				return undefined;
			}
			this.publish({ status: "ok", value });
			return value;
		} catch (error) {
			if (
				this.generation !== mine ||
				error instanceof QgisSdkBridgeAbortedError
			) {
				return undefined;
			}
			this.publish({ status: "error", error: asError(error) });
			return undefined;
		} finally {
			if (this.controller === controller) {
				this.controller = null;
			}
		}
	};
}

/** Options for {@link layersQuery}. */
export interface LayersQueryOptions {
	/** Items per page while following `next_cursor`; the host's default otherwise. */
	readonly pageSize?: number;
}

/**
 * Every vector layer of the project, following `layers.list` pages to the
 * end: what a layer picker binds to. Needs the `layers.read` grant.
 */
export function layersQuery(
	qgis: QgisSdkCore<unknown, unknown>,
	options: LayersQueryOptions = {},
): HostQueryStore<readonly VectorLayerInfo[]> {
	return new HostQueryStore(qgis, "layers.list", async (host, { signal }) => {
		const items: VectorLayerInfo[] = [];
		let cursor: string | undefined;
		do {
			const page: LayerPage = await host.layers.list(
				{
					...(cursor === undefined ? {} : { cursor }),
					...(options.pageSize === undefined
						? {}
						: { limit: options.pageSize }),
				},
				{ signal },
			);
			items.push(...page.items);
			cursor = page.next_cursor;
		} while (cursor !== undefined);
		return Object.freeze(items);
	});
}

/**
 * The field names of one vector layer, for a `field` input whose `of` names
 * a layer input: `layers.get` under the `layers.read` grant. A layer's CRS is
 * on the same reply; a project CRS query is not on the wire yet.
 */
export function layerFieldsQuery(
	qgis: QgisSdkCore<unknown, unknown>,
	layerId: string,
): HostQueryStore<readonly string[]> {
	return new HostQueryStore(qgis, "layers.get", async (host, { signal }) => {
		const layer = await host.layers.get({ layer_id: layerId }, { signal });
		return Object.freeze([...layer.field_names]);
	});
}
