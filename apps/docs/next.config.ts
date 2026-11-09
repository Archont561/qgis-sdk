import { createMDX } from "fumadocs-mdx/next";
import type { NextConfig } from "next";
import { BASE } from "./site";

// GitHub Pages serves a project site under the repository name, so `basePath`
// is the repository: `/qgis-sdk/`. `output: "export"` writes the whole site to
// `out/`, which is `apps/docs/dist`'s replacement - static files, no server.
const nextConfig: NextConfig = {
	output: "export",
	trailingSlash: true,
	basePath: BASE,
	images: { unoptimized: true },
	reactStrictMode: true,
};

export default createMDX()(nextConfig);
