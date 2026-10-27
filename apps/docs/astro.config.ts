import { existsSync } from "node:fs";
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";
import starlightLlmsMarkdown from "starlight-llms-markdown";
import { BASE, DESCRIPTION, REPOSITORY, SITE, TITLE } from "./site";
import { versions } from "./versions";

// The Storybook of packages/qgis-sdk-ui joins the site when its static build
// was copied in by scripts/generate.ts (the `docs-build` Pixi task does both).
const storybook = existsSync(
	new URL("./public/storybook/index.html", import.meta.url),
);

// Deployed to GitHub Pages by .github/workflows/docs.yml as a project site,
// hence `site` + `base`. Starlight bundles @astrojs/sitemap: `site` alone
// gives sitemap-index.xml, canonical URLs and absolute links in llms.txt.
export default defineConfig({
	site: SITE,
	base: BASE,
	trailingSlash: "always",
	vite: { define: { __QGIS_SDK_VERSIONS__: JSON.stringify(versions) } },
	integrations: [
		starlight({
			title: TITLE,
			description: DESCRIPTION,
			logo: { src: "./src/assets/logo.svg", alt: "" },
			favicon: "/favicon.svg",
			social: [{ icon: "github", label: "GitHub", href: REPOSITORY }],
			// Generated pages carry their own `editUrl` (the backlog guide they
			// render); this base serves the hand-written pages under src/.
			editLink: { baseUrl: `${REPOSITORY}/edit/main/apps/docs/` },
			lastUpdated: true,
			customCss: ["./src/styles/brand.css"],
			tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 3 },
			components: { Head: "./src/components/Head.astro" },
			sidebar: [
				{
					label: "Start here",
					items: [
						{ slug: "start/installation" },
						{ slug: "start/first-plugin" },
						{ slug: "start/concepts" },
					],
				},
				{
					label: "Python package",
					items: [{ autogenerate: { directory: "python" } }],
				},
				{
					label: "TypeScript SDK",
					items: [{ autogenerate: { directory: "typescript" } }],
				},
				{
					label: "Workspace and qualification",
					items: [
						{ autogenerate: { directory: "workspace", collapsed: true } },
					],
				},
				{
					label: "Reference",
					items: [{ slug: "reference/design-decisions" }],
				},
				{
					label: "Project",
					items: [
						...(storybook
							? [
									{
										label: "Component Storybook",
										link: "/storybook/",
										attrs: { target: "_blank" },
									},
								]
							: []),
						// Shipped artifacts only: releases and registries, never the
						// plans and tasks behind them.
						{ label: "Releases", link: `${REPOSITORY}/releases` },
					],
				},
			],
			plugins: [
				starlightLlmsMarkdown({
					sectionLabels: {
						start: "Start here",
						python: "Python package guide",
						typescript: "TypeScript SDK guide",
						workspace: "Workspace, harnesses and qualification evidence",
						reference: "Reference",
					},
					optionalLinks: [
						{
							title: "Repository",
							url: REPOSITORY,
							description: "Source, issues and releases.",
						},
					],
				}),
			],
		}),
	],
});
