---
id: decision-85
title: Keep the public API inventory committed, and rebuild the site from it
date: '2026-11-14'
status: accepted
---
## Context

`api/python.json` is generated (decision-56), so it is fair to ask why it is
also committed rather than written into the checkout by whatever build needs
it - the docs build, most obviously, at 57 KB and under a second to produce.

Three things read it, and two of them read the *committed* copy as evidence:

- `release verify-api --tag` diffs a tag against the working tree with
  `git show <tag>:api/python.json`. A gitignored file is in no tag, so every
  comparison reports every name as new.
- `release_verify_api --check` compares the tracked file to the tree. If CI
  generates the file first, the check compares the tree to itself and can no
  longer fail.
- A reviewer reads the diff. That is the reason the file is 990 lines of sorted
  names rather than a database: a rename shows up in review instead of at
  release time.

The repository already draws this line elsewhere. `bun.lock` and `pixi.lock`
are committed generated files, because their value is being reviewed;
`processing/native.py` and `apps/docs/lib/generated/` are ignored, because
their only value is being consumed. The inventory is the former.

## Decision

1. **The inventory stays committed.** Generating it per build would buy 57 KB
   and cost the per-tag diff, the freshness gate and the review surface.
   decision-56 point 5 already requires it to be tracked; this record says why.
2. **Every reader fails by naming `qgis-sdk api dump`.** `scripts/lib/inventory.ts`
   turns a missing file, a truncated write and a JSON document of the wrong
   shape into one sentence with the command that fixes it, and the API-index
   test reads through the same loader so the build and the suite cannot
   disagree about what a valid document is.
3. **The site rebuilds from it, and that list is tested.** `docs.yml` runs on
   `api/**` and `pixi.toml` alongside the paths it already had;
   `test_docs_workflow_rebuilds_the_site_for_every_input_the_renderer_reads`
   samples ten real inputs plus the built Storybook against both trigger lists,
   so an input that stops being covered fails the suite instead of shipping a
   stale page.

## Consequences

- A rename that reaches a green pull request reaches the deployed site in the
  same run; before this, `docs.yml` matched nothing under `apps/docs` and the
  reference index kept the old names until an unrelated change rebuilt it.
- `packages/*/src/**` stays out of the trigger list on purpose: an API change
  is only green once the inventory is re-dumped, so matching `api/**` covers
  it, and an internal refactor does not redeploy the site.
- The inventory cannot be removed from `.gitignore` without the release train
  losing its per-tag diff; that is the trade this record declines to make.
