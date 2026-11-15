/**
 * The components the registry must carry, as data.
 *
 * Kept apart from `mdx.tsx` for one practical reason: importing the registry
 * loads React and every Fumadocs component, which drags the presentational
 * components into the coverage report at zero and fails the site's 90% gate.
 * A test that reads this list imports nothing but a constant, and checks the
 * registry's source against it.
 *
 * The order is the order the phases of TASK-170 name them.
 */
export const COMPONENT_NAMES = [
	"Callout",
	"Card",
	"Cards",
	"Steps",
	"Step",
	"Tabs",
	"Tab",
	"Files",
	"Folder",
	"File",
	"TypeTable",
	"Accordion",
	"Accordions",
	"Banner",
	"InlineTOC",
	"ImageZoom",
] as const;
