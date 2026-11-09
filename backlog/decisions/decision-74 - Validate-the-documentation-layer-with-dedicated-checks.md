---
id: decision-74
title: Validate the documentation layer with dedicated checks
date: '2026-11-12'
status: accepted
---
## Context

The repository writes a great deal of prose and, until now, checked it with the
site's own tooling only: `docs-link-check` walks the exported tree, a Python
test compares the getting-started snippets with the sources they quote, and
`postbuild.ts` refuses to export a page without its markdown twin. Nothing
looked at the prose a reader meets first - the root landing page and the pages
that route them - and nothing looked at structure, style or the links between
files, so a broken relative link in the documentation layer was found by a
reader rather than by CI.

decision-29 fixed the landing page's shape and `tests/scripts/test_readme_shape.py`
enforces it, but the page itself was hand-edited, so each change to the badges
or the repository URL was an edit that could be forgotten. decision-73 moved
the site to Fumadocs and made the export verifiable; the layer above the site
had no equivalent.

## Decision

1. **`docs/` is the entry point to the documentation, and it is validated.**
   The directory states how documentation is written and checked here, and
   where each kind of knowledge lives: guides, concepts, reference,
   architecture, development. Its pages route to the canonical copy - the
   published site for readers, `backlog/decisions/` for records - instead of
   restating it, so there is still one explanation of anything.
2. **Four checks, one per concern.** alint keeps the repository conventions;
   markdownlint-cli2 keeps the Markdown structure; Vale keeps the writing
   style, with this repository's rules in `docs/vale/styles` rather than a
   downloaded style package; lychee keeps the links between files. A tool that
   also did prose would report the same defect twice, and a tool that did
   everything would be a tool nobody configures.
3. **The checks gate the merge.** `.github/workflows/docs-check.yml` runs the
   three prose checks on every pull request that can change them, and alint
   already runs in `Linux checks` on every pull request. A red check is a
   blocker, not advice.
4. **Links are checked offline.** `lychee` runs with `offline = true`: what
   fails is a path inside the repository that does not resolve, not a website
   that is briefly down. The published site's links stay with
   `docs-link-check`, which resolves them against the exported files.
5. **The landing page is generated.** `bun run readme` renders `README.md`
   from `scripts/readme/template.ejs` with readme-md-generator, taking the
   repository URL, homepage, license and badges from `package.json`. The
   template keeps the decision-29 shape, so the generated page passes the same
   test as before, and a moved repository or a renamed license is one edit
   instead of five.
6. **The style rules are this repository's own.** Two Vale rules ship:
   em dashes (the tree spells the pause `-`) and weasel words ("simply",
   "obviously"). Both are cheap, both are checkable, and neither pretends to
   judge whether the documentation is true - that stays a review question.

## Consequences

- A documentation-only change now costs a short job rather than nothing, and
  the job fails on the prose it changed instead of on a website.
- Vale and lychee are single binaries, so they are installed by pinned actions
  in the workflow and are not part of `restore.sh`; `pixi run -e bun lint-docs`
  runs the Markdown check alone, and the other two are a local install.
- The validation scope is the documentation layer: `docs/` and `README.md`.
  `backlog/` is a record store with its own conventions and
  `apps/docs/content/docs/` is generated, so linting either would report on
  text nobody edits by hand.
- The "definition of done" in `docs/README.md` makes the documentation
  assessment part of a change rather than a follow-up, and says so out loud
  when no documentation change is needed.
