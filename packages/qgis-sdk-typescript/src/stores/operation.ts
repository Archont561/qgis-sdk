/** {@link OperationStore}: one generated operation, latest run wins. */

import { QgisSdkBridgeAbortedError } from "../bridge";
import { asError, BaseStore } from "./base";

// ---------------------------------------------------------------------------
// OperationStore
// ---------------------------------------------------------------------------

/** Where one invocation stands. */
export type OperationState<R> =
	| { readonly status: "idle" }
	| { readonly status: "pending" }
	| { readonly status: "ok"; readonly value: R }
	| { readonly status: "error"; readonly error: Error };

/** An operation member of a generated map: input, optional signal, promise. */
export type Operation<I, R> = (
	input: I,
	options?: { readonly signal?: AbortSignal },
) => Promise<R>;

export const IDLE: OperationState<never> = Object.freeze({ status: "idle" });
const PENDING: OperationState<never> = Object.freeze({ status: "pending" });

/**
 * Run one generated operation.
 *
 * `run` resolves with the value, or with `undefined` when the call failed,
 * was aborted or was superseded by a later run - the state carries the error,
 * so the promise never rejects into an event handler. Only the latest run can
 * change the state. `abort` ends the in-flight call locally (the host may
 * still run it); `reset` aborts and returns to `idle`. The methods are bound,
 * so they can be passed around without the store.
 */
export class OperationStore<I, R> extends BaseStore<OperationState<R>> {
	private generation = 0;
	private controller: AbortController | null = null;

	public constructor(private readonly operation: Operation<I, R>) {
		super(IDLE);
	}

	public readonly abort = (): void => {
		this.generation += 1;
		this.controller?.abort();
		this.controller = null;
	};

	public readonly reset = (): void => {
		this.abort();
		this.publish(IDLE);
	};

	public readonly run = async (input: I): Promise<R | undefined> => {
		this.abort();
		const mine = this.generation;
		const controller = new AbortController();
		this.controller = controller;
		this.publish(PENDING);
		try {
			const value = await this.operation(input, { signal: controller.signal });
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
