/**
 * A consumer's own UnoCSS build: preset-mini unprefixed, preflight on, over
 * a page that uses the same utilities the catalogue does. Printed to stdout.
 *
 * Run in its own process: preset-mini writes a prefix into rule objects it
 * shares across instances, so the catalogue's `qs-` would leak into this
 * generator inside the test's process.
 */

import { createGenerator } from "@unocss/core";
import { presetMini } from "@unocss/preset-mini";

const PAGE = `<div class="flex inline-flex items-center gap-1 gap-2 border rounded bg-white text-base text-xs p-2 px-2 px-3 py-1 m-0 mt-1 mb-1 block w-full h-2 max-h-60 overflow-auto box-border flex-1 font-mono whitespace-pre-wrap">
	<button class="cursor-pointer focus-visible:outline-2 disabled:opacity-60 disabled:cursor-default"></button></div>`;

const generator = await createGenerator({ presets: [presetMini()] });
const result = await generator.generate(PAGE, { preflights: true });
process.stdout.write(result.css);
