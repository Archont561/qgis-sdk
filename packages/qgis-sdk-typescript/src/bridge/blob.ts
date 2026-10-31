/**
 * Reading a `BlobRef`: bounded chunks, assembled, then verified.
 *
 * A payload above the inline ceiling does not cross the channel in one message
 * (decision-59). The host keeps it, hands the page a `BlobRef` and answers
 * `blob.get` with one chunk at a time; this module is the loop that turns those
 * chunks back into bytes and refuses them if they are not the bytes the ref
 * named.
 *
 * Two rules, both about not trusting a length:
 *
 * - The assembled size must equal `ref.size`. A short read is a refusal, not a
 *   short payload, because a caller that received fewer bytes than the host
 *   promised has no way to tell a truncated stream from a different object.
 * - The SHA-256 of the assembled bytes must equal `ref.checksum`. The digest is
 *   computed here rather than through `crypto.subtle`, which a QWebEngine page
 *   served from `qrc:` does not expose; a verification that only works on one
 *   origin is not a verification.
 */

import { QgisSdkError } from "../errors";
import type { BlobChunk } from "./protocol";

/** A blob the page could not read, or read and could not verify. */
export class QgisSdkBridgeBlobError extends QgisSdkError {
	public readonly blobId: string;

	public constructor(blobId: string, message: string, code = "invalid_blob") {
		super(`${blobId}: ${message}`, code);
		this.blobId = blobId;
	}
}

/** The least of what a `BlobRef` has to say for this module to check it. */
export interface BlobDescriptor {
	readonly id: string;
	readonly size: number;
	readonly checksum: string;
}

/** What the caller passes to fetch one chunk: the host's `blob.get`. */
export type BlobFetcher = (
	input: Readonly<Record<string, unknown>>,
) => Promise<unknown>;

/** Options for {@link readBlob}. */
export interface ReadBlobOptions {
	/**
	 * Chunk size to ask for. The host caps it and refuses a larger request, so a
	 * caller that wants smaller chunks (to keep a UI responsive) may lower it.
	 */
	readonly chunkSize?: number;
	/** Called with bytes received so far after each chunk, for a progress bar. */
	readonly onProgress?: (received: number, total: number) => void;
}

/**
 * Fetch every chunk of `ref` and return the bytes, or throw.
 *
 * The loop follows `next_offset` instead of counting bytes: the host decides
 * where each chunk ends, and a client that computed the next offset itself would
 * silently skip data the moment the host's chunk size changed.
 */
export async function readBlob(
	fetch: BlobFetcher,
	ref: BlobDescriptor,
	options: ReadBlobOptions = {},
): Promise<Uint8Array> {
	if (!Number.isSafeInteger(ref.size) || ref.size < 0) {
		throw new QgisSdkBridgeBlobError(ref.id, "the ref carries no usable size");
	}
	const assembled: Uint8Array[] = [];
	let received = 0;
	let offset: number | null = 0;
	let guard = 0;
	const limit = Math.floor(ref.size / 1) + 2;
	while (offset !== null) {
		guard += 1;
		if (guard > limit) {
			throw new QgisSdkBridgeBlobError(
				ref.id,
				"the host kept returning chunks past the size it promised",
			);
		}
		const chunk = parseChunk(
			ref.id,
			await fetch({
				blob: ref,
				offset,
				...(options.chunkSize === undefined
					? {}
					: { length: options.chunkSize }),
			}),
		);
		if (chunk.offset !== offset) {
			throw new QgisSdkBridgeBlobError(
				ref.id,
				`asked for offset ${offset} and received ${chunk.offset}`,
			);
		}
		const bytes = decodeBase64(chunk.data_base64);
		if (bytes.length !== chunk.length) {
			throw new QgisSdkBridgeBlobError(
				ref.id,
				`chunk at ${chunk.offset} declares ${chunk.length} bytes and carries ${bytes.length}`,
			);
		}
		assembled.push(bytes);
		received += bytes.length;
		if (received > ref.size) {
			throw new QgisSdkBridgeBlobError(
				ref.id,
				"the chunks carry more bytes than the ref's size",
			);
		}
		options.onProgress?.(received, ref.size);
		offset = chunk.next_offset;
	}
	const bytes = concat(assembled, received);
	if (bytes.length !== ref.size) {
		throw new QgisSdkBridgeBlobError(
			ref.id,
			`assembled ${bytes.length} bytes and the ref promised ${ref.size}`,
		);
	}
	const checksum = sha256Hex(bytes);
	if (checksum !== ref.checksum) {
		throw new QgisSdkBridgeBlobError(
			ref.id,
			`checksum sha256:${checksum} does not match the ref's sha256:${ref.checksum}`,
			"blob_checksum_mismatch",
		);
	}
	return bytes;
}

/** Refuse a chunk shape the host could not legitimately have produced. */
function parseChunk(blobId: string, raw: unknown): BlobChunk {
	if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
		throw new QgisSdkBridgeBlobError(blobId, "a chunk must be an object");
	}
	const value = raw as Record<string, unknown>;
	const offset = value.offset;
	const length = value.length;
	const nextOffset = value.next_offset;
	if (!isIndex(offset) || !isIndex(length)) {
		throw new QgisSdkBridgeBlobError(
			blobId,
			"a chunk must name a non-negative offset and length",
		);
	}
	if (nextOffset !== null && !isIndex(nextOffset)) {
		throw new QgisSdkBridgeBlobError(
			blobId,
			"next_offset must be a non-negative integer or null",
		);
	}
	if (nextOffset !== null && nextOffset <= offset) {
		throw new QgisSdkBridgeBlobError(
			blobId,
			"next_offset must move forward, or the loop would never end",
		);
	}
	if (typeof value.data_base64 !== "string") {
		throw new QgisSdkBridgeBlobError(blobId, "a chunk carries no data");
	}
	if (typeof value.size !== "number" || typeof value.checksum !== "string") {
		throw new QgisSdkBridgeBlobError(
			blobId,
			"a chunk must repeat the size and checksum it belongs to",
		);
	}
	return {
		offset,
		length,
		size: value.size,
		media_type: typeof value.media_type === "string" ? value.media_type : "",
		checksum: value.checksum,
		data_base64: value.data_base64,
		next_offset: nextOffset,
	};
}

function isIndex(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function concat(parts: readonly Uint8Array[], size: number): Uint8Array {
	if (parts.length === 1) {
		const only = parts[0] as Uint8Array;
		return only.length === size ? only : only.slice();
	}
	const out = new Uint8Array(size);
	let at = 0;
	for (const part of parts) {
		out.set(part, at);
		at += part.length;
	}
	return out;
}

const BASE64_ALPHABET =
	"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

const BASE64_LOOKUP: Int16Array = (() => {
	const table = new Int16Array(128).fill(-1);
	for (let index = 0; index < BASE64_ALPHABET.length; index += 1) {
		table[BASE64_ALPHABET.charCodeAt(index)] = index;
	}
	return table;
})();

/**
 * Decode standard base64 without `atob`.
 *
 * `atob` exists in a browser and in Bun, but it silently ignores whitespace and
 * accepts a truncated payload; a decoder that refuses what it cannot read keeps
 * a corrupt chunk a failure instead of a shorter array.
 */
export function decodeBase64(text: string): Uint8Array {
	const stripped = text.replace(/=+$/, "");
	if (stripped.length % 4 === 1) {
		throw new QgisSdkBridgeBlobError("", "base64 length is impossible");
	}
	const out = new Uint8Array(Math.floor((stripped.length * 3) / 4));
	let buffer = 0;
	let bits = 0;
	let at = 0;
	for (let index = 0; index < stripped.length; index += 1) {
		const code = stripped.charCodeAt(index);
		const value = code < 128 ? BASE64_LOOKUP[code] : -1;
		if (value === undefined || value < 0) {
			throw new QgisSdkBridgeBlobError(
				"",
				"base64 carries a character it cannot",
			);
		}
		buffer = (buffer << 6) | value;
		bits += 6;
		if (bits >= 8) {
			bits -= 8;
			out[at] = (buffer >> bits) & 0xff;
			at += 1;
		}
	}
	return out.subarray(0, at);
}

const ROUND_CONSTANTS = new Uint32Array([
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
	0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
	0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
	0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
	0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
	0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
	0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
	0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
	0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

/**
 * SHA-256 of `bytes`, lowercase hex.
 *
 * Synchronous on purpose: the caller has already assembled a whole blob in
 * memory, so an async digest would buy nothing and cost a promise the type
 * system cannot make safe across `crypto.subtle`'s absence.
 */
export function sha256Hex(bytes: Uint8Array): string {
	const words = new Uint32Array(64);
	const state = new Uint32Array([
		0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
		0x1f83d9ab, 0x5be0cd19,
	]);
	const bitLength = bytes.length * 8;
	const padded = new Uint8Array((((bytes.length + 8) >> 6) + 1) << 6);
	padded.set(bytes);
	padded[bytes.length] = 0x80;
	const view = new DataView(padded.buffer);
	view.setUint32(padded.length - 8, Math.floor(bitLength / 0x100000000));
	view.setUint32(padded.length - 4, bitLength >>> 0);
	for (let block = 0; block < padded.length; block += 64) {
		for (let index = 0; index < 16; index += 1) {
			words[index] = view.getUint32(block + index * 4);
		}
		for (let index = 16; index < 64; index += 1) {
			const a = words[index - 15] ?? 0;
			const b = words[index - 2] ?? 0;
			const s0 = rotateRight(a, 7) ^ rotateRight(a, 18) ^ (a >>> 3);
			const s1 = rotateRight(b, 17) ^ rotateRight(b, 19) ^ (b >>> 10);
			words[index] =
				((words[index - 16] ?? 0) + s0 + (words[index - 7] ?? 0) + s1) >>> 0;
		}
		let a = state[0] ?? 0;
		let b = state[1] ?? 0;
		let c = state[2] ?? 0;
		let d = state[3] ?? 0;
		let e = state[4] ?? 0;
		let f = state[5] ?? 0;
		let g = state[6] ?? 0;
		let h = state[7] ?? 0;
		for (let index = 0; index < 64; index += 1) {
			const s1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
			const choice = (e & f) ^ (~e & g);
			const temp1 =
				(h +
					s1 +
					choice +
					(ROUND_CONSTANTS[index] ?? 0) +
					(words[index] ?? 0)) >>>
				0;
			const s0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
			const majority = (a & b) ^ (a & c) ^ (b & c);
			const temp2 = (s0 + majority) >>> 0;
			h = g;
			g = f;
			f = e;
			e = (d + temp1) >>> 0;
			d = c;
			c = b;
			b = a;
			a = (temp1 + temp2) >>> 0;
		}
		state[0] = ((state[0] ?? 0) + a) >>> 0;
		state[1] = ((state[1] ?? 0) + b) >>> 0;
		state[2] = ((state[2] ?? 0) + c) >>> 0;
		state[3] = ((state[3] ?? 0) + d) >>> 0;
		state[4] = ((state[4] ?? 0) + e) >>> 0;
		state[5] = ((state[5] ?? 0) + f) >>> 0;
		state[6] = ((state[6] ?? 0) + g) >>> 0;
		state[7] = ((state[7] ?? 0) + h) >>> 0;
	}
	let hex = "";
	for (const word of state) {
		hex += word.toString(16).padStart(8, "0");
	}
	return hex;
}

function rotateRight(value: number, by: number): number {
	return ((value >>> by) | (value << (32 - by))) >>> 0;
}
