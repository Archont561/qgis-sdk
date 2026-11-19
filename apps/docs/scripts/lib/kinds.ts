/**
 * The need a page serves, and the prose budget that need carries.
 *
 * Decision-86 scopes every page by the one reader need it answers - learning
 * (tutorial), doing (how-to), looking up (reference) or understanding
 * (explanation) - and records the kind in the page frontmatter. The budgets
 * are ceilings on prose words outside tables and code: a tutorial ends at
 * 1,200, a how-to at 700, a reference at 400, an explanation at 1,500.
 *
 * `PAGE_KINDS` is the editorial half: which need each guide-derived page
 * serves, keyed by the page path the generator writes it to (no extension).
 * The generator looks every page up here and fails on one it does not know,
 * so a new section cannot ship without a declared kind. Hand-written pages
 * carry their kind in their own frontmatter; the two generated reference
 * pages (`api-index`, `design-decisions`) carry theirs from their generators.
 *
 * The fumero reference (`reference/python/`) is not in this map: it is
 * generated from docstrings, which carry their own budget (CC101), and it is
 * excluded from the prose metric for the same reason.
 */

/** The four reader needs a page can serve. */
export type Kind = "tutorial" | "how-to" | "reference" | "explanation";

/** The prose ceiling each kind carries, in words outside tables and code. */
export const KIND_BUDGETS: Readonly<Record<Kind, number>> = {
	tutorial: 1200,
	"how-to": 700,
	reference: 400,
	explanation: 1500,
};

/** The kinds, for validating a frontmatter value. */
export const KINDS: readonly Kind[] = [
	"tutorial",
	"how-to",
	"reference",
	"explanation",
];

/** Whether a frontmatter value is a kind. */
export function isKind(value: string): value is Kind {
	return (KINDS as readonly string[]).includes(value);
}

/**
 * The kind of every guide-derived page, by the path the generator writes it
 * to. A page that answers two needs is classified by the one it answers most;
 * the budget file records the rest as a reason when it is over budget.
 */
export const PAGE_KINDS: Readonly<Record<string, Kind>> = {
	// doc-12: the Python package guide.
	"python/index": "explanation",
	"python/installation": "tutorial",
	"python/supported-targets": "reference",
	"python/stability": "reference",
	"python/declarations": "how-to",
	"python/pure-contract-layer": "explanation",
	"python/scoped-plugin-runtime": "explanation",
	"python/desktop-host-host-and-the-project-manifest": "explanation",
	"python/forms-an-actions-inputs-as-a-window": "how-to",
	"python/desktop-bindings-and-native-surfaces": "explanation",
	"python/processing-algorithms-and-safe-outputs": "how-to",
	"python/features-expressions-and-editing": "how-to",
	"python/the-map-canvas": "how-to",
	"python/rasters": "how-to",
	"python/layer-kinds-mesh-point-cloud-vector-tile-annotation-and-tiled-scene":
		"how-to",
	"python/print-layouts-and-atlases": "how-to",
	"python/symbology-labelling-and-the-style-manager": "how-to",
	"python/connections-and-authentication-configurations": "how-to",
	"python/the-project": "how-to",
	"python/providers-algorithms-in-the-qgis-processing-toolbox": "how-to",
	"python/webengine-bridge-host-side": "explanation",
	"python/networking": "how-to",
	"python/scoped-jobs": "how-to",
	"python/project-scaffold": "tutorial",
	"python/grants-the-console-and-the-http-allowlist": "reference",
	"python/project-checks": "reference",
	"python/running-tests-qgis-sdk-test": "how-to",
	"python/developing-against-qgis-qgis-sdk-dev": "tutorial",
	"python/from-the-qgis-python-console": "tutorial",
	"python/running-an-app-qgis-sdk-run": "tutorial",
	"python/building-an-installable-zip-qgis-sdk-build": "tutorial",
	"python/optional-controlled-deployment-adapter": "explanation",
	"python/troubleshooting": "how-to",
	"python/ide-autocompletion-and-typing": "how-to",
	"python/going-deeper-where-this-contract-stops": "explanation",
	"python/migration/v0-1-experimental-policy": "reference",
	"python/migration/v0-2": "reference",
	"python/migration/v0-3": "reference",
	"python/migration/v0-4": "reference",
	"python/migration/v0-5": "reference",
	"python/migration/v0-6": "reference",
	"python/migration/v0-7": "reference",
	"python/migration/v0-8": "reference",
	"python/migration/v0-9": "reference",
	"python/migration/v0-10": "reference",
	"python/migration/v0-11": "reference",

	// doc-13: the TypeScript SDK guide.
	"typescript/index": "explanation",
	"typescript/installation": "tutorial",
	"typescript/exports": "reference",
	"typescript/transport-client": "how-to",
	"typescript/host-namespaces": "explanation",
	"typescript/the-schema-module-and-qgissdk": "explanation",
	"typescript/stores-the-framework-free-core": "explanation",
	"typescript/react-bindings": "how-to",
	"typescript/vue-bindings": "how-to",
	"typescript/svelte-bindings": "how-to",
	"typescript/components-archont561qgis-sdk-ui": "reference",
	"typescript/testing-against-a-scripted-host": "how-to",
	"typescript/migration/v0-2": "reference",
	"typescript/migration/v0-3": "reference",
	"typescript/migration/v0-4": "reference",
	"typescript/migration/v0-5": "reference",
	"typescript/migration/v0-6": "reference",
	"typescript/migration/v0-7": "reference",
	"typescript/migration/v0-8": "reference",

	// doc-14: the workspace, harnesses and evidence.
	"contributing/workspace/index": "explanation",
	"contributing/workspace/quick-start": "tutorial",
	"contributing/workspace/development-environments": "tutorial",
	"contributing/workspace/reproducible-sandbox": "tutorial",
	"contributing/workspace/test-build-and-the-pixi-tasks": "how-to",
	"contributing/workspace/repository-layout": "reference",
	"contributing/workspace/documentation-site": "explanation",
	"contributing/workspace/contributing": "how-to",
	"contributing/workspace/python-package-development": "tutorial",
	"contributing/workspace/test-layers": "explanation",
	"contributing/workspace/contract-generation-checked-example": "tutorial",
	"contributing/workspace/build-artifacts": "reference",
	"contributing/workspace/developer-scripts": "reference",
	"contributing/workspace/headless-qgis-and-webengine-qualification":
		"explanation",
	"contributing/workspace/desktop-lifecycle-harnesses": "explanation",
	"contributing/workspace/040-release-gate-2026-10-25": "reference",
	"contributing/workspace/050-release-gate-2026-10-25": "reference",
	"contributing/workspace/060-release-gate-2026-10-26": "reference",
	"contributing/workspace/split-release-pipeline-rehearsal": "reference",
	"contributing/workspace/ui-release-train-rehearsal-2026-10-27": "reference",
	"contributing/workspace/070-triple-rehearsal-2026-10-27": "reference",
	"contributing/workspace/070-release-gate-2026-10-27": "reference",
	"contributing/workspace/080-release-gate-2026-10-29": "reference",
	"contributing/workspace/080-rehearsal-2026-10-29": "reference",
	"contributing/workspace/090-release-gate-2026-10-31": "reference",
	"contributing/workspace/0100-release-gate-2026-11-06": "reference",
	"contributing/workspace/0100-rc-rehearsal-2026-11-06": "reference",
	"contributing/workspace/0110-release-gate-2026-11-07": "reference",
	"contributing/workspace/0110-rc-rehearsal-2026-11-07": "reference",
};

/** The kind of a guide-derived page, or an error naming the page. */
export function kindOf(path: string): Kind {
	const kind = PAGE_KINDS[path];
	if (kind === undefined) {
		throw new Error(
			`${path}: no kind in scripts/lib/kinds.ts; a page must declare the need it serves`,
		);
	}
	return kind;
}
