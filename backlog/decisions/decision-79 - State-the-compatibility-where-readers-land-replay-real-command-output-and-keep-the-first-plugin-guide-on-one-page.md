---
id: decision-79
title: State the compatibility on the page a reader lands on, replay real command output, and keep the guide on one page
date: '2026-11-10'
status: accepted
---
## Context

Three things a reader met on the site were true and hard to use.

The support matrix states which QGIS and Python combinations are qualified, but
it states them on a reference page: the landing page said nothing, so a reader
who installed first and read later found out from a failing command. The FAQ
answers "which QGIS versions" - and a reader looking for a version notice does
not open a FAQ.

The reference answered questions well and a newcomer still had to hop: install on
one page, scaffold on another, the declaration model on a third, the check codes
on a fourth. Each hop is a chance to lose the thread, and the first plugin was
the one walk where every step was already known.

The Storybook served at `/storybook/` is the preview of the UI catalogue, and it
ignored the site's theme: a reader in dark mode met a light frame around light
previews, because the manager follows the OS alone and the `theme` global was
pinned to `light`.

## Decision

1. **The landing page states the compatibility, and reads it from the matrix.**
   `scripts/lib/compat.ts` parses `support-matrix:begin/end` out of the Python
   guide into `lib/generated/compat.json` - qualified rows only, series newest
   first, the LTS label taken from the row whose evidence says LTS - and
   `components/compat-notice.tsx` renders one sentence: QGIS series, Python
   range, "and nothing else is tested", plus the link to the rows. The install
   page carries the same component, so the notice a reader lands on and the
   notice where they install cannot disagree.
2. **The Storybook follows the site's theme, not the OS.** `manager.ts` picks the
   manager base theme from `localStorage.theme` (falling back to
   `prefers-color-scheme`), and `preview.ts` seeds the `theme` global the same
   way and listens for the `storage` event, so a toggle in the site reaches a
   running preview. The toolbar still overrides per session.
3. **The first-plugin guide is one page, start to finish.** `start/first-plugin`
   now carries install, scaffold, the declaration model in four sentences, test,
   check, `dev` and build, with the commands and their real output inline. Links
   appear only at the end, for what comes after a first plugin works.
4. **A walkthrough is a component over a real transcript, not a screenshot.**
   `CliWalkthrough` shows the command, a file tree that opens a file per click
   (scaffold) or a transcript that types itself out with a replay button
   (`check`). Transcripts live in `components/walkthroughs.ts` and were captured
   from runs of the scaffold on this tree; reduced-motion readers get the whole
   transcript at once.

## Alternatives considered

- **A static line on the landing page** ("QGIS 4 and 3.44, Python 3.11+"). What
  it says today it says forever; the matrix moves, and the promise that outlives
  a qualification row is exactly the failure the matrix exists to avoid.
- **A compatibility badge component per page**, fetched at runtime. Rejected:
  the numbers are build-time facts, and a runtime fetch turns a static page into
  one that needs a server or a failing request.
- **Moving the FAQ above the fold instead of a notice.** A FAQ is a destination;
  a reader deciding whether to install needs the constraint where they are
  deciding.
- **Patching the copied Storybook's HTML to force a dark class.** The manager's
  palette is set through `addons.setConfig({ theme })`; appending CSS to a built
  bundle is a fork of somebody else's UI, and it breaks on their next release.
- **Keeping the guide linked rather than inlined** ("no page hopping" versus
  "one canonical explanation per topic"). The reference pages stay canonical for
  declarations and checks; the guide repeats the minimum needed to finish, and
  says so, because the reader mid-walk is not looking for the reference.

## Consequences

- The landing page and the install page can only state versions the matrix
  qualifies; adding a row changes the sentence without anyone editing prose.
- `apps/docs/tests/compat.test.ts` holds the parser: qualified rows only, newest
  first, the LTS label from the row, and an empty answer for a guide without a
  matrix.
- The Storybook build now reads a key it does not own (`localStorage.theme`).
  It is read, not written, and every path falls back to the OS preference.
- The first-plugin page is longer and duplicates four facts the reference pages
  also state. That is the cost of the walk; the duplication is named in its
  opening paragraph rather than hidden.
- The walkthrough data is a second copy of the scaffold's text. A change to the
  scaffold is a change to `walkthroughs.ts`, and the capture command is in the
  file's docstring.
