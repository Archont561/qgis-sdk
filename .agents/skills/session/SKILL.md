---
name: session
description: Guide a normal work session in this QGIS SDK workspace from orientation through implementation, merge readiness, and post-merge handoff. Use at the start or resumption of repository work, when choosing backlog work, when preparing or completing a PR/direct merge, and when the user asks for a session report or next-session prompt. For an explicit, scoped request, proceed without imposing a proposal-and-wait gate.
---

# Workspace session lifecycle

Use this skill to preserve context and evidence across ordinary work sessions and merges. Follow the repository's [AGENTS.md](../../../AGENTS.md) rules. Do not claim a task, test, merge, CI run, or backlog update without evidence.

## 1. Restore and orient at start or resumption

1. Start a repository session by checking whether this is a Git checkout. When it is, run `bash scripts/restore.sh` from the repository root before any Pixi install, test, lint, or build command. The script selects the published bundle from `pixi-sandbox.toml` and restores the developer environment; let it complete and report any failure rather than silently substituting a different setup. If Git metadata or the published branch is unavailable, state the blocker and use an already-available environment only if it is valid for the requested task. If this is not a Git checkout, do not invoke the restore script or invent branch/remote state.
2. After restore, read root `AGENTS.md` and the relevant skill(s). For Python/TypeScript/QGIS workspace-specific details, also consult [`qgis-sdk`](../qgis-sdk/SKILL.md).
3. Inspect Git status, current branch, and configured remotes when Git metadata is available. Do not fabricate branch, commit, PR, or merge state.
4. Inspect the relevant package files and existing tests. Read repository documentation only as needed for the request.
5. When the user asks what to work on or asks to select backlog work, use the [`backlog`](../backlog/SKILL.md) CLI workflow, read candidate tasks and dependencies, then present a small evidence-based proposal and wait. Do not add this pause to an explicit, scoped task.

### First-run workspace dependencies

After restore and orientation, prepare dependencies before running workspace checks:

- Ensure `pixi` is on `PATH`. If restore materialised it but user-tool registration did not complete, prepend the repository's `.pixi/tools/<platform>` directory (for example, `export PATH="$PWD/.pixi/tools/linux-64:$PATH"` on Linux x86-64). Keep this path available to nested package scripts too; do not substitute a system Python or Bun.
- A restored Pixi environment does not provide the workspace's JavaScript `node_modules`. On the first run in a fresh checkout, or if dependencies are missing (for example, `turbo: command not found`), run this from the repository root before retrying the requested check:

  ```sh
  pixi run -e bun bun install --frozen-lockfile
  ```

  This downloads the locked JavaScript dependencies using Bun in its separate Pixi environment. Reuse an already-installed workspace on later runs; do not reinstall on every command.
- If downloads are blocked or the frozen install fails, report the command and blocker. Do not drop `--frozen-lockfile`, regenerate lockfiles, upgrade dependencies, or silently switch package managers to get past the failure. Confirm setup did not change tracked dependency files.
- A successful dependency install does not resolve a failed restore or its integrity warnings. Report those separately. If the user explicitly asks to run checks with the partially restored environment, preserve it and the Pixi lockfile with `export PIXI_FROZEN=true PIXI_NO_INSTALL=true` for both setup and checks (including nested `pixi run` calls), and qualify the results as using an unverified restore. Do not claim full environment verification.

## 2. Scope the work

- Restate the requested outcome internally as observable acceptance criteria; ask only about ambiguity that would materially change the implementation.
- For behavior changes and bug fixes, follow [`tdd`](../tdd/SKILL.md). For behavior-preserving structural work, follow [`refactor`](../refactor/SKILL.md); use [`clean-code-principles`](../clean-code-principles/SKILL.md) when evaluating design choices.
- If a matching backlog task exists, read it and use the Backlog.md CLI to update task state. Do not create a task merely to represent an already explicit one-turn request unless asked or the work needs persistent tracking.

## 3. Implement and verify

- Keep source-based tests in the existing package test directories. Avoid unrelated scope and generated artifacts.
- Use Pixi environments and root scripts:

  ```sh
  pixi run -e bun bun run test       # local tests, no coverage gate
  pixi run -e bun bun run coverage  # separate Python/TypeScript 90% checks
  pixi run -e bun bun run build
  pixi run -e bun typecheck
  ```

- Run the narrowest relevant check first, then the appropriate root check. Report exact commands and outcomes. If a check cannot run, state why instead of implying success.
- Keep Python development tools in `packages/qgis-sdk/pyproject.toml`'s `dev` extra; Pixi installs that local extra through the Python feature. Keep direct Pixi pins exact, Bun separate, and Codecov LCOV paths repository-root-relative.

## 4. Prepare a normal merge

A passing local check is not permission to merge. Before a merge:

1. Inspect the final diff and confirm it matches the approved scope.
2. Run the relevant tests/coverage/build checks and validate a conventional commit message through the repository's Convco hook/task when committing.
3. Confirm the target branch/PR and required CI checks if GitHub access is available. Report inaccessible checks as unverified.
4. Merge or push only when the user explicitly authorizes that action. Respect the repo's stated merge method; if none is specified, ask before choosing a non-obvious strategy. Never force-push or rewrite shared history without explicit authorization.
5. If Git metadata, remote access, or permissions are unavailable, stop at merge readiness and explain the blocker.

## 5. Close the session after merge

When a PR is merged or an authorized direct push lands on the target branch:

1. Verify the landed commit with Git when available. Check post-merge CI/workflow results if accessible; distinguish passed, failed, and unavailable checks.
2. Update any associated backlog task using the CLI only after its acceptance criteria are proven. Leave unverified criteria open and name the missing evidence.
3. Provide a concise session report with: **merged status and PR/SHA**, **work completed**, **validation and CI results**, **open items/blockers**, and a **next-session opening prompt**. If nothing merged, say so and still identify the current state and next step.

Do not run this post-merge closeout before a merge has actually landed; for a pre-merge review, report readiness and remaining checks instead.
