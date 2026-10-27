/** The store contract and the base every store extends (see `../stores.ts`). */

import { QgisSdkError } from "../errors";

/** A store was built or driven outside the shape it needs. */
export class QgisSdkStoreError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "store_binding");
	}
}

// ---------------------------------------------------------------------------
// The contract
// ---------------------------------------------------------------------------

/** What a listener receives: the whole snapshot, never a diff. */
export type StoreListener<T> = (snapshot: T) => void;

/**
 * The contract every store honours, and the one `useSyncExternalStore`,
 * Vue's `shallowRef` wiring and Svelte's `$store` all read.
 */
export interface Store<T> {
	/** The current value; the same object until the next change. Bound. */
	readonly getSnapshot: () => T;
	/**
	 * Call `listener` now and after every change; the returned function
	 * stops the calls. Bound. Svelte passes a second `invalidate` argument,
	 * which is ignored.
	 */
	readonly subscribe: (listener: StoreListener<T>) => () => void;
}

export abstract class BaseStore<T> implements Store<T> {
	private snapshot: T;
	private readonly listeners = new Set<StoreListener<T>>();

	protected constructor(initial: T) {
		this.snapshot = initial;
	}

	// Bound, so `useSyncExternalStore(store.subscribe, store.getSnapshot)`
	// needs no wrapper.
	public readonly getSnapshot = (): T => this.snapshot;

	public readonly subscribe = (listener: StoreListener<T>): (() => void) => {
		this.listeners.add(listener);
		listener(this.snapshot);
		return () => {
			this.listeners.delete(listener);
		};
	};

	protected publish(next: T): void {
		if (Object.is(next, this.snapshot)) {
			return;
		}
		this.snapshot = next;
		for (const listener of [...this.listeners]) {
			listener(next);
		}
	}
}

export function asError(error: unknown): Error {
	return error instanceof Error ? error : new Error(String(error));
}
