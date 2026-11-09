---
id: decision-73
title: Render the documentation site with Fumadocs on Next and keep the export static
date: '2026-11-11'
status: accepted
---
## Context

decision-29 made the site the place the reference prose is read, and TASK-43
built it as Astro Starlight. decision-71 is unrelated; what changed is the
renderer.

The site outgrew what Starlight was bought for. Four things were hand-built on
top of it and each one leaned on a Starlight internal: the guides are split
into pages by our own generator with `slug`, `sidebar` and `editUrl`
frontmatter; the migration notes needed a sibling directory and a `slug` to be
grouped under their guide; `starlight-llms-markdown` produced `llms.txt` and
the `.md` twins with no way to ask it whether every page got one; and the
design-decisions page needed raw HTML inside Markdown table cells, which the
markdown parser a table goes through does not keep. Two of the three bugs that
took the longest to find in 0.11.0 were this kind - a page that rendered, and
its twin that did not.

## Decision

1. **Fumadocs on Next, statically exported.** The site is `apps/docs` on
   Fumadocs UI and Next with `output: "export"`: `next build` writes `out/`,
   GitHub Pages serves it, and nothing at runtime touches a server. The
   content collection is `content/docs/`, the routes are unchanged
   (`/python/installation/`), `basePath` is `/qgis-sdk` and `trailingSlash`
   is on, so every published URL, redirect and inbound link survives.
2. **Links are root-relative.** Next adds `basePath` when it renders a link,
   so content writes `/python/installation/` and the generator prefixes
   nothing. The plain `<a>` elements on the landing page carry `BASE`
   themselves because nothing is added for them.
3. **The export is ours to verify.** `scripts/postbuild.ts` writes
   `llms.txt`, `llms-full.txt`, one `.md` per page, the sitemap and the
   compatibility pages, and then checks them: a rendered page without a
   markdown export, or a page missing from the index, fails the build. The
   export is a file tree we can test rather than a plugin's output we hope is
   complete.
4. **Search stays client-side.** The index is exported at build time
   (`staticGET` in `app/api/search/route.ts`) and the dialog downloads it.
   Static hosting rules out server-side search; it does not rule out search.
5. **Node joins Bun in the docs build.** The Pixi `bun` environment pins Bun
   alone, so the docs job also runs `actions/setup-node`: Bun installs and
   drives the workspace, Next builds and renders with Node. A Node runtime is
   therefore a local prerequisite for `bun run build` and `bun run dev` in
   `apps/docs`, and `pixi.lock` stays as it is.
6. **No MCP endpoint.** An MCP server needs a process, and GitHub Pages has
   none. The agent surface is the static one: `llms.txt`, `llms-full.txt` and
   a `.md` beside every page. A hosted MCP server is a separate decision with
   its own hosting dependency.

## Consequences

- The generator writes `meta.json` per folder instead of Starlight
  frontmatter, and `lib/generated/` instead of `vite.define`: the sidebar's
  order and the landing page's versions are data now.
- The design-decisions page is `.mdx`, because a table cell parses as prose
  and cannot carry the `#decision-N` anchor. The anchors stand in one block
  above the table.
- `@astrojs/sitemap` is gone with Starlight; `scripts/lib/sitemap.ts` writes
  the same two file names so `robots.txt` and the redirect check are unchanged.
- A draft migration note renders as a callout only if its admonition markers
  stand alone as paragraphs; `draftNotice()` in `scripts/lib/guides.ts` writes
  them that way and a test pins it.
- The docs build has one more moving part (Node) than 0.11.0, and the
  `docs.yml` job says why.
