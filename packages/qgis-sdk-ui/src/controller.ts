/**
 * The join between a store and a Lit element.
 *
 * A store (decision-47) owns the behaviour: it validates, calls the host,
 * publishes snapshots. An element only subscribes, and Lit only needs to be
 * told when to re-render. `StoreController` is that one sentence as a
 * `ReactiveController`: it subscribes while the host element is connected,
 * unsubscribes when it leaves the document, re-subscribes when the store is
 * swapped, and asks the host for an update on every snapshot.
 */

import type { Store } from "@archont561/qgis-sdk";
import type { ReactiveController, ReactiveControllerHost } from "lit";

export class StoreController<T> implements ReactiveController {
	private current: Store<T> | null;
	private snapshot: T | undefined = undefined;
	private stop: (() => void) | null = null;
	private connected = false;

	public constructor(
		private readonly host: ReactiveControllerHost,
		store: Store<T> | null = null,
	) {
		this.current = store;
		host.addController(this);
	}

	/** The store being followed; `null` follows nothing. */
	public get store(): Store<T> | null {
		return this.current;
	}

	public set store(next: Store<T> | null) {
		if (Object.is(next, this.current)) {
			return;
		}
		this.unsubscribe();
		this.current = next;
		this.snapshot = undefined;
		if (this.connected) {
			this.subscribe();
		}
	}

	/** The latest snapshot, `undefined` before the first or without a store. */
	public get value(): T | undefined {
		return this.snapshot;
	}

	public hostConnected(): void {
		this.connected = true;
		this.subscribe();
	}

	public hostDisconnected(): void {
		this.connected = false;
		this.unsubscribe();
	}

	private subscribe(): void {
		if (this.current === null || this.stop !== null) {
			return;
		}
		this.stop = this.current.subscribe((snapshot) => {
			this.snapshot = snapshot;
			this.host.requestUpdate();
		});
	}

	private unsubscribe(): void {
		this.stop?.();
		this.stop = null;
	}
}
