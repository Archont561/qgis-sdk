/**
 * Helpers the entry points share but the package does not export.
 *
 * Nothing here is part of the public surface: a page that needs a record guard
 * writes its own one-liner rather than depending on an SDK implementation
 * detail that may move.
 */

import type { StreamEventKind } from "./declarations";

/** The declared stream event kinds; the declaration parser and the frame parser check the same list. */
export const STREAM_EVENT_KINDS: readonly StreamEventKind[] = Object.freeze([
	"data",
	"progress",
	"state",
]);

/**
 * Return whether `value` is a non-null, non-array object: the shape every wire
 * envelope, description and event payload must have before its fields are read.
 */
export function isPlainRecord(
	value: unknown,
): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}
