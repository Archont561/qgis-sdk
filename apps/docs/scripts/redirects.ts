/** Add legacy routes after the Astro build, without indexing them as content. */
import { fileURLToPath } from "node:url";
import {
	LEGACY_ROUTES,
	verifyRedirectSurfaces,
	writeRedirects,
} from "./lib/redirects";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
await writeRedirects(dist, LEGACY_ROUTES);
await verifyRedirectSurfaces(dist, LEGACY_ROUTES);
console.log(
	`redirects: wrote ${Object.keys(LEGACY_ROUTES).length} compatibility pages`,
);
