/**
 * Fail when the built site under `dist/` (or the directory given) has an
 * internal link to a missing page, file or fragment.
 *
 *     bun run scripts/check-links.ts [dist]
 */
import { BASE } from "../site";
import { checkLinks } from "./lib/links";

const dist = process.argv[2] ?? new URL("../dist/", import.meta.url).pathname;
const report = await checkLinks(dist, { base: BASE });
for (const link of report.broken) {
	console.error(`check-links: ${link.page}: ${link.href}: ${link.reason}`);
}
console.log(
	`check-links: ${report.checked} internal links on ${report.pages} pages, ${report.broken.length} broken`,
);
if (report.broken.length > 0) {
	process.exit(1);
}
