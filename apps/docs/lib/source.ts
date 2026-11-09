/** The content collection as Fumadocs reads it: pages, page tree, static params. */
import { docs } from "collections/server";
import { loader } from "fumadocs-core/source";

// `baseUrl: "/"` keeps the routes the guides have always had
// (`/python/installation/`, not `/docs/python/installation/`): the basePath of
// the deployment is added by Next, not by the loader.
export const source = loader({
	baseUrl: "/",
	source: docs.toFumadocsSource(),
});
