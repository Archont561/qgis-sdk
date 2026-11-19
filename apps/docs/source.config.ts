import { remarkAdmonition } from "fumadocs-core/mdx-plugins";
import { pageSchema } from "fumadocs-core/source/schema";
import { defineConfig, defineDocs } from "fumadocs-mdx/config";

// The content collection: `content/docs/**` becomes the page tree. The
// generated half of it is written by `scripts/generate.ts` before the build;
// the hand-written half is in git.
export const docs = defineDocs({
	dir: "content/docs",
	docs: {
		// Loose rather than the default, because the Python reference is written
		// by fumero and carries its own `_fumero` key: the kind of page it is,
		// which `components/mdx/pdx-plugin.tsx` labels in the sidebar. Fumadocs
		// keeps only the frontmatter its schema names, so a strict schema would
		// drop the key and the labels with it (decision-86).
		schema: pageSchema.loose(),
		// `page.data.getText("processed")` then answers the markdown the build
		// rendered, which the llms export writes beside each page.
		postprocess: { includeProcessedMarkdown: true },
	},
});

export default defineConfig({
	mdxOptions: {
		// The generator writes `:::warn` for a page whose notes describe a line
		// still being cut; this is what turns it into a callout.
		remarkPlugins: [remarkAdmonition],
	},
});
