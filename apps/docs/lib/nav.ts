/**
 * The site's navigation, shared by the landing page and the docs layout, so a
 * reader meets the same links wherever they land.
 */
import { existsSync } from "node:fs";
import { join } from "node:path";
import type { LinkItemType } from "fumadocs-ui/layouts/shared";
import { REPOSITORY } from "@/site";

/** `scripts/generate.ts` copies the Storybook here when it was built. */
export const hasStorybook = existsSync(
	join(process.cwd(), "public/storybook/index.html"),
);

export const navLinks: LinkItemType[] = [
	{ type: "main", text: "Start", url: "/start/installation" },
	{ type: "main", text: "Python", url: "/python" },
	{ type: "main", text: "TypeScript", url: "/typescript" },
	{
		type: "main",
		text: "Releases",
		url: `${REPOSITORY}/releases`,
		external: true,
	},
	...(hasStorybook
		? [
				{
					type: "main" as const,
					text: "Storybook",
					url: "/storybook/",
					external: true,
				},
			]
		: []),
];
