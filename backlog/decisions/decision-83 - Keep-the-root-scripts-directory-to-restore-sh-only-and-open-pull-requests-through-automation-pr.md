---
id: decision-83
title: Keep the root `scripts/` directory to `restore.sh` only, and open pull requests through `automation/pr`
date: '2026-11-12'
status: accepted
---
## Context

Two different kinds of file had drifted into places where no gate looked at them.

**`scripts/` was three jobs in one directory.** It held `restore.sh` - the
sandbox entry point documented in the README, in the session skill and in the
arena skill, a file whose whole contract is that it runs before Pixi exists -
and it also held the two JavaScript tools that maintain generated files:
`readme/generate.mjs` with `readme/template.ejs` (the root landing page, via
readme-md-generator) and `agents/refresh.mjs` (the marked regions of
`AGENTS.md`, via `@eugeniughelbur/agents-md`). Every other piece of repository
tooling lives in `automation/`, is importable, and is covered by
`tests/scripts`. These two were not: nothing but `package.json` named them, so a
typo in a path was a CI-only discovery, and the directory mixed "the one script
you run before anything works" with "a build step".

**Pull requests were opened by hand.** Each one was a `git push`, a `gh pr
create`, and then - because a body had been written in a heredoc and came out
wrong - a `gh api -X PATCH --input body.json` to repair it. Nothing about that
sequence is repository-specific, which is exactly why it kept being retyped:
the title came from a commit that had to be read first, the body from the commit
list, and the branch had to exist on the remote before GitHub would accept the
request. The watcher (`automation/pr.py watch`) already answered "is it green?";
the creation half had no owner.

## Decision

**Everything that runs lives in `automation/`, and `scripts/` is `restore.sh`.**

1. `scripts/readme/` and `scripts/agents/` moved to `automation/readme/` and
   `automation/agents/`. Both wrappers already resolved the repository root from
   their own location, so the move is a path rename in `package.json`
   (`bun run readme`, `bun run agents`, `bun run agents:check`) and in the
   `docs-check.yml` path filter, which now watches `automation/readme/**`.
2. **alint enforces the directory, not a document.** `.alint.yml` gains
   `dir_only_contains` rules that allow exactly `restore.sh` under `scripts/`.
   Two rules are needed because the rule kind matches direct children only:
   `select: "scripts"` covers a file at the top, `select: "scripts/**"` covers
   anything nested. `tests/alint/test_policy.py` proves both, and that the one
   allowed file passes.
3. **`python -m automation.pr` is the way a pull request is opened and
   watched.** `open` reads the current branch, the default branch, and the
   commit subjects the base does not have; it pushes with `--set-upstream`,
   refuses a branch that already has a pull request, and passes the commit list
   as the default body. `--title`, `--body`, `--body-file`, `--base` and
   `--draft` override that. `pixi run automation pr_open` drives the same
   command line, so the task and the module cannot drift apart, and
   `pixi run automation pr_watch` keeps the polling half.
4. AGENTS.md states both: the `scripts/` rule with the alint rule names, and
   "open and watch pull requests through `automation.pr`, never a hand-written
   `gh` sequence", including the two GitHub quirks that made the old sequence
   fail (`gh pr edit` on the retired GraphQL `projectCards`, and `gh api -f`
   sending strings rather than JSON types).

## Consequences

- A new script has one obvious home, and adding one to `scripts/` fails at the
  repository-policy step rather than at review time.
- `restore.sh` stays where every document says it is; nothing about the sandbox
  bootstrap changes.
- The PR body is the commit list unless someone writes one, so a change with a
  good commit history needs no body work at all - and a change that has to
  explain itself writes the body once, in a file.
- The watcher and the opener share one module and one exit-status vocabulary
  (`0` fine, `1` refused or failed, `127` `gh`/`git` failed).
