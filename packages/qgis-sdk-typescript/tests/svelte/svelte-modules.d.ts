// The `.svelte` fixtures under this directory are compiled at test time by
// the Bun plugin `tests/svelte.test.ts` registers; TypeScript only needs to
// know they are components.
declare module "*.svelte" {
	// biome-ignore lint/suspicious/noExplicitAny: a fixture's props are its own
	const component: import("svelte").Component<any>;
	export default component;
}
