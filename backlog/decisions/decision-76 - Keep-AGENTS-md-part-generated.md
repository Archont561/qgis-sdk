---
id: decision-76
title: Keep AGENTS.md part generated
date: '2026-11-13'
status: accepted
---
## Context

`AGENTS.md` had grown into the file every agent reads first: merge rules, the
TDD and BDD order, the `pathlib` rule Ruff enforces, the naming rule for
exception classes, the Pixi and Bun commands. All of it was written by hand, and
the parts that drift are not the rules - they are the facts underneath them. The
top-level layout changed twice in the last two migrations, and a line sending an
agent to `apps/docs/src/` outlives the directory by months.

`@eugeniughelbur/agents-md` generates exactly those facts from the repository -
overview, top-level layout, default branch, remote - and refreshes only the
regions it owns, wrapped in `agents-md:begin`/`agents-md:end` markers. It reads
`package.json` first, though, and this checkout's front door is a `package.json`
for the JavaScript workspace: the tool reports a Node repository with `npm run
test` and a "node (typescript)" stack, none of which is true of a Python SDK
whose environments are Pixi and whose JavaScript runs on Bun.

## Decision

1. **Adopt the marker contract, not the generated file.** Three regions -
   Overview, Project structure and Git & PR workflow - sit between markers and
   belong to the generator. Every rule stays outside them, written by hand, and
   the tool's own contract guarantees it is never touched.
2. **Correct the detection in one place.** `scripts/agents/refresh.mjs` runs the
   generator and then rewrites the two things it gets wrong here: the stack
   sentence (Python and TypeScript, Pixi and Bun) and the stub sentences it
   leaves where it cannot tell. The correction is a wrapper rather than a fork so
   the tool keeps its own behaviour and its own upgrades.
3. **Staleness is a red check.** `bun run agents:check` regenerates into memory
   and fails when the file would change, so `Linux checks` catches an
   `AGENTS.md` that no longer matches the tree in the same run that catches a
   stale generated client.
4. **One source file, no symlink.** The tool offers to symlink `CLAUDE.md` to
   `AGENTS.md`; this repository keeps one file, because the skills under
   `.agents/skills/` and every agent in use here read `AGENTS.md` directly and a
   second name for the same content is a second thing to forget to update.
5. **The facts that need judgement stay out of the markers.** Where the SDK's
   tests live, which directories matter, why the stack is what it is - a
   generator cannot derive those, so the wrapper writes them as prose around the
   detected list instead of leaving a `TBD` stub inside a region that is
   refreshed on the next run.

## Consequences

- Changing the top-level layout, the default branch or the remote is followed by
  `bun run agents`; the CI check fails until the file agrees with the tree.
- The wrapper depends on the generator's current wording: it isolates the
  `package.json` description by splitting on `" Stack: "` and removes `_TBD: ..._`
  sentences. A release of the tool that rewords those sections fails the check
  loudly rather than writing a wrong sentence, which is the behaviour wanted from
  a dependency whose output becomes instructions.
- `AGENTS.md` now opens by saying which of its parts are generated, so a reader
  (or an agent) knows which lines to fix and which to regenerate.
- The generated regions are five lines of facts; the file's value is still the
  rules, and those are still reviewed by hand.
