/**
 * Progress, log and run button: the elements that show what the host is
 * doing. Driven by properties and by stores through readers; the run button
 * submits a form store or runs an operation store (task-70 AC #1).
 */

import { afterAll, describe, expect, test } from "bun:test";
import { formStore, OperationStore } from "@archont561/qgis-sdk";
import { fault } from "@archont561/qgis-sdk/testing";
import { install, tick, uninstall } from "./support/dom";
import { sdkWithHarness } from "./support/schema";

install();
afterAll(uninstall);

const { html } = await import("lit");
const { mount, one, ui } = await import("./support/elements");

type Progress = InstanceType<typeof ui.QgisJobProgress>;
type LogView = InstanceType<typeof ui.QgisLogView>;
type RunButton = InstanceType<typeof ui.QgisRunButton>;

describe("qgis-job-progress", () => {
	test("properties drive the bar, the text and the cancel button", async () => {
		const cancelled: string[] = [];
		const root = await mount(
			html`<qgis-job-progress label="Buffer" status="pending" .fraction=${0.25} message="Reading" .cancel=${() => cancelled.push("called")}></qgis-job-progress>`,
		);
		const bar = one<HTMLProgressElement>(root, "progress");
		const label = one<HTMLElement>(root, "[data-part='label']");
		expect(bar.getAttribute("value")).toBe("0.25");
		expect(bar.getAttribute("aria-busy")).toBe("true");
		expect(bar.getAttribute("aria-labelledby")).toBe(label.id);
		expect(bar.dataset.status).toBe("pending");
		expect(one<HTMLOutputElement>(root, "output").textContent).toBe("Reading");
		root.addEventListener("qgis-cancel", () => cancelled.push("event"));
		one<HTMLButtonElement>(root, "[data-part='cancel']").click();
		expect(cancelled).toEqual(["event", "called"]);

		const element = one<Progress>(root, "qgis-job-progress");
		element.status = "ok";
		element.message = "";
		element.fraction = 2;
		await tick();
		expect(root.querySelector("[data-part='cancel']")).toBeNull();
		expect(bar.getAttribute("value")).toBe("1");
		expect(one<HTMLOutputElement>(root, "output").textContent).toBe("Done");
		element.status = "error";
		element.fraction = null;
		await tick();
		expect(bar.hasAttribute("value")).toBe(false);
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toBe(
			"Failed",
		);
		element.status = "idle";
		await tick();
		expect(bar.getAttribute("value")).toBe("0");
		expect(one<HTMLOutputElement>(root, "output").textContent).toBe("");
	});

	test("an operation store is read through readProgress, a form through its submission", async () => {
		let release: ((value: { id: string }) => void) | null = null;
		const operation = new OperationStore<string, { id: string }>(
			() =>
				new Promise((resolve) => {
					release = resolve;
				}),
		);
		const root = await mount(
			html`<qgis-job-progress .store=${operation}></qgis-job-progress>`,
		);
		const element = one<Progress>(root, "qgis-job-progress");
		expect(element.progress).toEqual({ status: "idle", fraction: null });
		const run = operation.run("x");
		await tick();
		expect(element.progress.status).toBe("pending");
		expect(
			one<HTMLProgressElement>(root, "progress").hasAttribute("value"),
		).toBe(false);
		(release as unknown as (value: { id: string }) => void)({ id: "1" });
		await run;
		await tick();
		expect(element.progress).toEqual({ status: "ok", fraction: 1 });

		expect(
			ui.readProgress({
				submission: { status: "error", error: new Error("no") },
			}),
		).toEqual({
			status: "error",
			fraction: null,
			message: "no",
		});
		expect(ui.readProgress({ status: "open" })).toEqual({
			status: "pending",
			fraction: null,
		});
		expect(ui.readProgress({ status: "ended" })).toEqual({
			status: "ok",
			fraction: 1,
		});
		expect(ui.readProgress({ status: "failed", message: "x" })).toEqual({
			status: "error",
			fraction: null,
			message: "x",
		});
		expect(
			ui.readProgress({ status: "pending", fraction: 0.5, message: "half" }),
		).toEqual({
			status: "pending",
			fraction: 0.5,
			message: "half",
		});
		expect(ui.readProgress(42)).toEqual({ status: "idle" });
		expect(ui.readProgress({})).toEqual({ status: "idle", fraction: null });

		// A reader of the page's own maps anything.
		element.read = (snapshot) => ({
			status: "pending",
			fraction: (snapshot as { done: number }).done / 4,
		});
		element.store = {
			getSnapshot: () => ({ done: 1 }),
			subscribe: (listener) => {
				listener({ done: 1 });
				return () => undefined;
			},
		};
		await tick();
		expect(
			one<HTMLProgressElement>(root, "progress").getAttribute("value"),
		).toBe("0.25");
		element.store = null;
		await tick();
		expect(element.progress.status).toBe("idle");
	});
});

describe("qgis-log-view", () => {
	test("renders lines in a live log region, appends, trims to the limit, clears", async () => {
		const root = await mount(
			html`<qgis-log-view label="Log" .lines=${["a", "b"]} .limit=${3} clearable></qgis-log-view>`,
		);
		const pre = one<HTMLPreElement>(root, "pre");
		expect(pre.getAttribute("role")).toBe("log");
		expect(pre.getAttribute("aria-live")).toBe("polite");
		expect(pre.getAttribute("aria-labelledby")).toBe(
			one<HTMLElement>(root, "[data-part='label']").id,
		);
		expect(pre.textContent).toBe("a\nb");
		const view = one<LogView>(root, "qgis-log-view");
		view.append("c", "d");
		await tick();
		expect(pre.textContent).toBe("b\nc\nd");
		const clear = one<HTMLButtonElement>(root, "[data-part='clear']");
		expect(clear.disabled).toBe(false);
		clear.click();
		await tick();
		expect(pre.textContent).toBe("");
		expect(clear.disabled).toBe(true);
	});

	test("a store's readings accumulate; the default reader knows arrays, lines and stream events", async () => {
		let listener: ((snapshot: unknown) => void) | null = null;
		let snapshot: unknown = { lastEvent: null };
		const store = {
			getSnapshot: () => snapshot,
			subscribe: (next: (snapshot: unknown) => void) => {
				listener = next;
				next(snapshot);
				return () => undefined;
			},
		};
		const root = await mount(
			html`<qgis-log-view .store=${store}></qgis-log-view>`,
		);
		const pre = one<HTMLPreElement>(root, "pre");
		expect(pre.textContent).toBe("");
		const publish = (next: unknown): void => {
			snapshot = next;
			(listener as unknown as (snapshot: unknown) => void)(next);
		};
		publish({ lastEvent: { message: "started" } });
		await tick();
		publish({ lastEvent: "plain" });
		await tick();
		publish({ lines: ["x", 1] });
		await tick();
		publish(["y"]);
		await tick();
		publish({ lastEvent: { other: true } });
		await tick();
		expect(pre.textContent).toBe("started\nplain\nx\n1\ny");
		expect(ui.readLines(null)).toEqual([]);
	});
});

describe("qgis-run-button", () => {
	test("submits a form store, is busy while pending, raises qgis-result", async () => {
		const { harness, qgis } = sdkWithHarness();
		let release: (() => void) | null = null;
		harness.expectInvoke("buffer", (payload) => {
			expect(payload).toEqual({ layer_id: "roads-1", distance_metres: 5 });
			return new Promise((resolve) => {
				release = () => resolve({ id: "done" });
			});
		});
		const form = formStore(qgis, "buffer", {
			initial: { layer_id: "roads-1", distance_metres: 5 },
		});
		const root = await mount(
			html`<qgis-run-button label="Go" pending-label="Going" .form=${form}></qgis-run-button>`,
		);
		const results: unknown[] = [];
		root.addEventListener("qgis-result", (event) =>
			results.push((event as CustomEvent).detail),
		);
		const button = one<HTMLButtonElement>(root, "button");
		expect(button.type).toBe("submit");
		expect(button.textContent).toBe("Go");
		button.click();
		await tick(1);
		expect(button.disabled).toBe(true);
		expect(button.getAttribute("aria-busy")).toBe("true");
		expect(button.textContent).toBe("Going");
		(release as unknown as () => void)();
		await harness.settled();
		await tick();
		expect(button.disabled).toBe(false);
		expect(results).toEqual([{ id: "done" }]);
		harness.assertSatisfied();
		qgis.close();
	});

	test("runs an operation store with its input; a failure raises no result", async () => {
		const { harness, qgis } = sdkWithHarness();
		harness.expectInvoke("buffer", () => fault("internal", "boom"));
		const operation = new OperationStore(qgis.buffer);
		const root = await mount(
			html`<qgis-run-button .operation=${operation} .input=${{ layer_id: "a", distance_metres: 1 }} error="shown"></qgis-run-button>`,
		);
		const events: string[] = [];
		root.addEventListener("qgis-run", () => events.push("run"));
		root.addEventListener("qgis-result", () => events.push("result"));
		const button = one<HTMLButtonElement>(root, "button");
		expect(button.type).toBe("button");
		expect(button.textContent).toBe("Run");
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toBe(
			"shown",
		);
		const element = one<RunButton>(root, "qgis-run-button");
		expect(await element.run()).toBeUndefined();
		await tick();
		expect(events).toEqual(["run"]);
		expect(operation.getSnapshot()).toMatchObject({ status: "error" });
		harness.assertSatisfied();
		qgis.close();
	});

	test("with no store it is a plain button", async () => {
		const root = await mount(html`<qgis-run-button></qgis-run-button>`);
		const events: string[] = [];
		root.addEventListener("qgis-run", () => events.push("run"));
		one<HTMLButtonElement>(root, "button").click();
		await tick();
		expect(events).toEqual(["run"]);
		expect(one<RunButton>(root, "qgis-run-button").pending).toBe(false);
	});
});
