"use client";

/**
 * A command, what it wrote, and what it said.
 *
 * The guides are read by someone with a terminal open, so the scaffold walk is a
 * file tree they click through and the check walk is the output arriving a line
 * at a time - the two things a screenshot cannot do. Nothing is fetched: the
 * transcripts are in `walkthroughs.ts`, so the page stays static and the
 * component ships no data of its own.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { WALKTHROUGHS, type WalkthroughFile } from "./walkthroughs";

interface Node {
	readonly name: string;
	readonly path: string;
	readonly file?: WalkthroughFile;
	readonly children: Node[];
}

function tree(files: readonly WalkthroughFile[]): Node[] {
	const root: Node = { name: "", path: "", children: [] };
	for (const file of files) {
		const parts = file.path.split("/");
		let current = root;
		parts.forEach((part, index) => {
			const path = parts.slice(0, index + 1).join("/");
			let next = current.children.find((child) => child.name === part);
			if (next === undefined) {
				next = { name: part, path, children: [] };
				current.children.push(next);
			}
			if (index === parts.length - 1) {
				next = { ...next, file };
				current.children[current.children.indexOf(next)] = next;
			}
			current = next;
		});
	}
	return root.children;
}

function FileIcon() {
	return (
		<svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5 shrink-0">
			<path
				fill="currentColor"
				d="M4 1.5A1.5 1.5 0 0 1 5.5 0h3.8L13 3.7V14.5A1.5 1.5 0 0 1 11.5 16h-6A1.5 1.5 0 0 1 4 14.5Zm5 .9V4h1.6Z"
			/>
		</svg>
	);
}

function FolderIcon({ open }: { open: boolean }) {
	return (
		<svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5 shrink-0">
			<path
				fill="currentColor"
				d={
					open
						? "M1 4.5A1.5 1.5 0 0 1 2.5 3h3.1l1.4 1.5h6A1.5 1.5 0 0 1 14.5 6v.5H4.2L1.6 13H2.5A1.5 1.5 0 0 1 1 11.5Zm3.4 3h10.2l-2.3 6.4a1.5 1.5 0 0 1-1.4 1H2.6Z"
						: "M1.5 3.5A1.5 1.5 0 0 1 3 2h3l1.5 1.5H13A1.5 1.5 0 0 1 14.5 5v7.5A1.5 1.5 0 0 1 13 14H3a1.5 1.5 0 0 1-1.5-1.5Z"
				}
			/>
		</svg>
	);
}

const LINE_DELAY_MS = 260;

export function CliWalkthrough({ name }: { name: string }) {
	const walkthrough = WALKTHROUGHS[name];
	const nodes = useMemo(() => tree(walkthrough?.files ?? []), [walkthrough]);
	const [selected, setSelected] = useState<string>(
		walkthrough?.terminal ? "" : (walkthrough?.files[0]?.path ?? ""),
	);
	const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
	const [printed, setPrinted] = useState(0);
	const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

	const lines = walkthrough?.terminal ?? [];
	const animate = useCallback(() => {
		setPrinted(0);
	}, []);

	useEffect(() => {
		if (lines.length === 0) {
			return;
		}
		if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
			setPrinted(lines.length);
			return;
		}
		animate();
	}, [animate, lines.length]);

	useEffect(() => {
		if (lines.length === 0 || printed >= lines.length) {
			return;
		}
		timer.current = setTimeout(
			() => setPrinted((count) => count + 1),
			LINE_DELAY_MS,
		);
		return () => {
			if (timer.current !== null) {
				clearTimeout(timer.current);
			}
		};
	}, [lines.length, printed]);

	if (walkthrough === undefined) {
		return null;
	}

	const file = walkthrough.files.find(
		(candidate) => candidate.path === selected,
	);
	const showingTerminal = walkthrough.terminal !== undefined && selected === "";

	const toggle = (path: string) => {
		setCollapsed((current) => {
			const next = new Set(current);
			if (next.has(path)) {
				next.delete(path);
			} else {
				next.add(path);
			}
			return next;
		});
	};

	const render = (entries: readonly Node[], depth = 0): React.ReactNode =>
		entries.map((node) => {
			const open = !collapsed.has(node.path);
			if (node.file === undefined) {
				return (
					<div key={node.path}>
						<button
							type="button"
							aria-expanded={open}
							onClick={() => toggle(node.path)}
							className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-fd-muted-foreground text-xs hover:bg-fd-accent"
							style={{ paddingLeft: `${depth * 12 + 6}px` }}
						>
							<FolderIcon open={open} />
							<span className="truncate">{node.name}</span>
						</button>
						{open && render(node.children, depth + 1)}
					</div>
				);
			}
			const active = node.path === selected;
			return (
				<button
					key={node.path}
					type="button"
					aria-current={active ? "true" : undefined}
					onClick={() => setSelected(node.path)}
					className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs ${
						active
							? "bg-fd-primary/10 font-medium text-fd-foreground"
							: "text-fd-muted-foreground hover:bg-fd-accent"
					}`}
					style={{ paddingLeft: `${depth * 12 + 6}px` }}
				>
					<FileIcon />
					<span className="truncate">{node.name}</span>
				</button>
			);
		});

	return (
		<figure className="cli-walkthrough not-prose my-6 overflow-hidden rounded-xl border bg-fd-card text-sm">
			<div className="flex items-center gap-2 border-b bg-fd-muted px-3 py-2 font-mono text-xs">
				<span aria-hidden="true" className="text-fd-muted-foreground">
					$
				</span>
				<code className="truncate">{walkthrough.command}</code>
				{walkthrough.terminal !== undefined && (
					<button
						type="button"
						onClick={animate}
						className="ml-auto rounded border px-2 py-0.5 text-[11px] text-fd-muted-foreground hover:bg-fd-accent"
					>
						Replay
					</button>
				)}
			</div>
			<div className="grid gap-0 sm:grid-cols-[minmax(9rem,14rem)_1fr]">
				<nav
					aria-label={`Files from ${walkthrough.command}`}
					className="border-b p-2 sm:border-r sm:border-b-0"
				>
					{walkthrough.terminal !== undefined && (
						<button
							type="button"
							aria-current={showingTerminal ? "true" : undefined}
							onClick={() => setSelected("")}
							className={`mb-1 flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs ${
								showingTerminal
									? "bg-fd-primary/10 font-medium text-fd-foreground"
									: "text-fd-muted-foreground hover:bg-fd-accent"
							}`}
						>
							<span aria-hidden="true" className="font-mono">
								{">_"}
							</span>
							<span>Output</span>
						</button>
					)}
					{render(nodes)}
				</nav>
				<div className="min-w-0">
					{showingTerminal ? (
						<div
							role="log"
							aria-live="polite"
							aria-label="Command output"
							className="h-full max-h-80 overflow-auto bg-fd-background p-3 font-mono text-xs leading-relaxed"
						>
							{lines.slice(0, printed).map((line, index) => (
								<div
									// biome-ignore lint/suspicious/noArrayIndexKey: a transcript line is its position
									key={index}
									className={
										line.startsWith("    ")
											? "pl-4 text-fd-muted-foreground"
											: line.startsWith("checked")
												? "mt-2 text-fd-foreground"
												: "text-fd-destructive"
									}
								>
									{line}
								</div>
							))}
							{printed < lines.length && (
								<span aria-hidden="true" className="animate-pulse">
									▌
								</span>
							)}
						</div>
					) : (
						<div className="max-h-80 overflow-auto">
							<div className="sticky top-0 border-b bg-fd-card px-3 py-1.5 font-mono text-[11px] text-fd-muted-foreground">
								{file?.path ?? ""}
							</div>
							<pre className="overflow-x-auto p-3 font-mono text-xs leading-relaxed">
								<code>{file?.content ?? ""}</code>
							</pre>
						</div>
					)}
				</div>
			</div>
			<figcaption className="border-t px-3 py-2 text-fd-muted-foreground text-xs">
				{walkthrough.caption}
			</figcaption>
		</figure>
	);
}
