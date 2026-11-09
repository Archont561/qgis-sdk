import { remarkAdmonition } from "fumadocs-core/mdx-plugins";
import { defineConfig, defineDocs } from "fumadocs-mdx/config";

// The content collection: `content/docs/**` becomes the page tree. The
// generated half of it is written by `scripts/generate.ts` before the build;
// the hand-written half is in git.
export const docs = defineDocs({
	dir: "content/docs",
	docs: {
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
