/**
 * The search index, exported at build time.
 *
 * `staticGET` answers the exported database instead of query results: GitHub
 * Pages serves files, not queries, so the dialog downloads this once and
 * searches in the browser. `force-static` is what makes `output: "export"`
 * write it to `out/api/search`.
 */
import { createFromSource } from "fumadocs-core/search/server";
import { source } from "@/lib/source";

export const dynamic = "force-static";

export const { staticGET: GET } = createFromSource(source, {
	language: "english",
});
