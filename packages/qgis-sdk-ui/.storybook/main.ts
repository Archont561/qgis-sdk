/**
 * Storybook over the catalogue (task-70 AC #2, #7): the Vite builder for
 * web components, the a11y addon, and the built `dist/` served statically so
 * `preview-head.html` can link the compiled `style.css` and `tokens.css`
 * exactly as a consumer does. `bun run storybook` builds first.
 */

import type { StorybookConfig } from "@storybook/web-components-vite";

const config: StorybookConfig = {
	framework: "@storybook/web-components-vite",
	stories: ["../stories/**/*.stories.ts"],
	addons: ["@storybook/addon-a11y"],
	staticDirs: [{ from: "../dist", to: "/dist" }],
	core: { disableTelemetry: true },
};

export default config;
