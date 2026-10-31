/**
 * Blobs above the inline ceiling, and following a stream across a gap.
 *
 * decision-59 asks two things of the page: verify what it fetched against the
 * checksum the host put in the ref, and acknowledge the stream frames it
 * delivered so the host can apply backpressure. Both are checked here against
 * the scripted harness - mock evidence about what the page does with a host that
 * behaves, never a claim about QWebEngine.
 */

import { createHash } from "node:crypto";
import { expect, test } from "@archont561/bun-test-utils";
import {
	type BlobChunk,
	BridgeClient,
	decodeBase64,
	followSubscription,
	QgisSdkBridgeBlobError,
	readBlob,
	sha256Hex,
} from "../src/bridge";
import { createBridgeHarness, type ScriptedStream } from "../src/testing";

function digest(bytes: Uint8Array): string {
	return createHash("sha256").update(bytes).digest("hex");
}

function toBase64(bytes: Uint8Array): string {
	return Buffer.from(bytes).toString("base64");
}

/** A fake `blob.get` over one payload, chunked the way the host chunks it. */
function chunked(
	payload: Uint8Array,
	size: number,
): (input: {
	readonly offset?: number;
	readonly length?: number;
}) => Promise<BlobChunk> {
	const checksum = digest(payload);
	return async (input) => {
		const offset = input.offset ?? 0;
		let length = Math.min(size, payload.length - offset);
		if (input.length !== undefined) {
			length = Math.min(length, input.length);
		}
		const slice = payload.subarray(offset, offset + length);
		const next = offset + length;
		return {
			offset,
			length,
			size: payload.length,
			media_type: "application/octet-stream",
			checksum,
			data_base64: toBase64(slice),
			next_offset: next >= payload.length ? null : next,
		};
	};
}

test("sha256 matches the vectors everyone tests against", () => {
	expect(sha256Hex(new Uint8Array())).toBe(
		"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
	);
	expect(sha256Hex(new TextEncoder().encode("abc"))).toBe(
		"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
	);
	// The padding boundaries: 55 bytes still fits one block, 56 needs two.
	for (const length of [1, 55, 56, 63, 64, 65, 119, 120, 1000]) {
		const bytes = new Uint8Array(length).fill(length % 256);
		expect(sha256Hex(bytes)).toBe(digest(bytes));
	}
});

test("base64 decodes exactly, and refuses what it cannot read", () => {
	expect(Array.from(decodeBase64(""))).toEqual([]);
	expect(new TextDecoder().decode(decodeBase64("aGVsbG8gd29ybGQ="))).toBe(
		"hello world",
	);
	expect(Array.from(decodeBase64("AAEC"))).toEqual([0, 1, 2]);
	expect(() => decodeBase64("a b")).toThrow(QgisSdkBridgeBlobError);
	expect(() => decodeBase64("a")).toThrow(QgisSdkBridgeBlobError);
});

test("a blob is fetched chunk by chunk and verified against its ref", async () => {
	const payload = new Uint8Array(10_000);
	for (let index = 0; index < payload.length; index += 1) {
		payload[index] = index % 251;
	}
	const ref = {
		id: "a".repeat(32),
		size: payload.length,
		checksum: digest(payload),
	};
	const seen: number[] = [];

	const bytes = await readBlob(chunked(payload, 512), ref, {
		onProgress: (received) => seen.push(received),
	});

	expect(bytes.length).toBe(payload.length);
	expect(Buffer.from(bytes).equals(Buffer.from(payload))).toBe(true);
	expect(seen.at(-1)).toBe(payload.length);
});

test("a blob whose bytes do not match its checksum is refused, not returned", async () => {
	const payload = new Uint8Array([1, 2, 3, 4]);
	const ref = {
		id: "b".repeat(32),
		size: 4,
		checksum: digest(new Uint8Array([9, 9, 9, 9])),
	};

	await expect(readBlob(chunked(payload, 2), ref)).rejects.toMatchObject({
		code: "blob_checksum_mismatch",
	});
});

test("a short read is a refusal, because a shorter payload is a different one", async () => {
	const payload = new Uint8Array([1, 2, 3, 4]);
	const ref = { id: "c".repeat(32), size: 6, checksum: digest(payload) };

	await expect(readBlob(chunked(payload, 2), ref)).rejects.toBeInstanceOf(
		QgisSdkBridgeBlobError,
	);
});

test("a chunk that does not move forward cannot loop forever", async () => {
	const stray = async (): Promise<BlobChunk> => ({
		offset: 0,
		length: 4,
		size: 8,
		media_type: "application/octet-stream",
		checksum: "0".repeat(64),
		data_base64: toBase64(new Uint8Array([1, 2, 3, 4])),
		next_offset: 0,
	});

	await expect(
		readBlob(stray, { id: "d".repeat(32), size: 8, checksum: "0".repeat(64) }),
	).rejects.toThrow(/must move forward/);
});

test("a chunk carrying more bytes than the ref promised is refused", async () => {
	const stray = async (): Promise<BlobChunk> => ({
		offset: 0,
		length: 8,
		size: 4,
		media_type: "application/octet-stream",
		checksum: "0".repeat(64),
		data_base64: toBase64(new Uint8Array(8)),
		next_offset: null,
	});

	await expect(
		readBlob(stray, { id: "e".repeat(32), size: 4, checksum: "0".repeat(64) }),
	).rejects.toThrow(/more bytes/);
});

test("the client acknowledges every frame it delivered, and never a terminal", async () => {
	const harness = createBridgeHarness<"demo.ticks">();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("demo.ticks", (_payload, opened) => {
		stream = opened;
	});
	const client = new BridgeClient(harness);
	const events: unknown[] = [];

	await client.subscribe(
		"demo.ticks",
		{},
		{
			onEvent: (event) => events.push(event.payload),
		},
	);
	stream?.emit("data", 1);
	stream?.emit("data", 2);
	await harness.settled();
	stream?.end({ kind: "complete" });
	await harness.settled();

	expect(events).toEqual([1, 2]);
	expect(harness.acknowledgements).toEqual([0, 1]);
	// The terminal is not acknowledged: the stream is over, and making the end
	// wait for a delivery receipt would let a stalled page keep it alive.
	expect(harness.acknowledgements).not.toContain(2);
	client.close();
});

test("a client can be built without acknowledgements, and then sends none", async () => {
	const harness = createBridgeHarness<"demo.ticks">();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("demo.ticks", (_payload, opened) => {
		stream = opened;
	});
	const client = new BridgeClient(harness, { acknowledge: false });

	await client.subscribe("demo.ticks");
	stream?.emit("data", 1);
	await harness.settled();

	expect(harness.acknowledgements).toEqual([]);
	client.close();
});

test("a stream that ends in a gap is reopened, and the resume says what was lost", async () => {
	const harness = createBridgeHarness<"demo.ticks">();
	const opened: ScriptedStream[] = [];
	harness.expectSubscribe("demo.ticks", (_payload, stream) => {
		opened.push(stream);
	});
	harness.expectSubscribe("demo.ticks", (_payload, stream) => {
		opened.push(stream);
	});
	const client = new BridgeClient(harness);
	const resumes: { attempt: number; dropped: number }[] = [];
	const terminals: string[] = [];

	const followed = followSubscription(
		client,
		"demo.ticks",
		{},
		{ onTerminal: (terminal) => terminals.push(terminal.kind) },
		{
			onResume: (info) =>
				resumes.push({ attempt: info.attempt, dropped: info.dropped }),
		},
	);
	await followed.ready;
	expect(followed.attempts).toBe(1);

	opened[0]?.skip(3);
	opened[0]?.emit("data", 1);
	await harness.settled();
	await harness.settled();

	expect(resumes).toEqual([{ attempt: 2, dropped: 3 }]);
	expect(followed.attempts).toBe(2);
	expect(terminals).toEqual(["gap"]);

	followed.close();
	await harness.settled();
	expect(followed.closed).toBe(true);
	client.close();
});

test("following stops after the configured number of reopens", async () => {
	const harness = createBridgeHarness<"demo.ticks">();
	const opened: ScriptedStream[] = [];
	for (let index = 0; index < 2; index += 1) {
		harness.expectSubscribe("demo.ticks", (_payload, stream) => {
			opened.push(stream);
		});
	}
	const client = new BridgeClient(harness);
	const terminals: string[] = [];

	const followed = followSubscription(
		client,
		"demo.ticks",
		{},
		{ onTerminal: (terminal) => terminals.push(terminal.kind) },
		{ maxResubscribes: 1 },
	);
	await followed.ready;
	opened[0]?.skip(1);
	opened[0]?.emit("data", 1);
	await harness.settled();
	await harness.settled();
	expect(followed.attempts).toBe(2);

	await harness.settled();
	opened[1]?.skip(1);
	opened[1]?.emit("data", 1);
	await harness.settled();

	expect(followed.attempts).toBe(2);
	expect(followed.closed).toBe(true);
	expect(terminals).toEqual(["gap", "gap"]);
	client.close();
});
