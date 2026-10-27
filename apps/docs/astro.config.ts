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
				// The migration notes render into a sibling directory and are routed
				// under the guide with `slug`, so they can sit in one collapsed
				// subgroup at the bottom of the guide instead of among its sections.
				{
					label: "Python package",
					items: [
						{ autogenerate: { directory: "python" } },
						{
							label: "Migration notes",
							collapsed: true,
							items: [{ autogenerate: { directory: "python-migration" } }],
						},
					],
				},
				{
					label: "TypeScript SDK",
					items: [
						{ autogenerate: { directory: "typescript" } },
						{
							label: "Migration notes",
							collapsed: true,
							items: [{ autogenerate: { directory: "typescript-migration" } }],
						},
					],
				},
				{
					label: "Reference",
					items: [{ slug: "reference/design-decisions" }],
				},
				{
					label: "Contributing",
					collapsed: true,
					items: [
						{
							label: "Workspace, harnesses, and evidence",
							collapsed: true,
							items: [
								{ autogenerate: { directory: "contributing/workspace" } },
							],
						},
					],
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
						"python/migration": "Python migration notes",
						typescript: "TypeScript SDK guide",
						"typescript/migration": "TypeScript migration notes",
						reference: "Reference",
						contributing: "Contributing",
						"contributing/workspace": "Workspace, harnesses, and evidence",
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
