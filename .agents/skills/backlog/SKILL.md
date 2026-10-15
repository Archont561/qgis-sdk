---
name: backlog
description: Manage this workspace's Markdown tasks through Backlog.md. Use when creating, splitting, selecting, tracking, or closing tasks, or when the user mentions the backlog, task IDs, acceptance criteria, or a Definition of Done.
---

Backlog tasks live as Markdown under `backlog/`. Use the CLI for task metadata so IDs, dependencies, filenames, and status stay consistent. Do not invent tasks when the backlog has no matching work.

## Run the CLI in this workspace

`backlog.md` is a root Bun workspace dependency. Run it through Pixi's separate Bun environment:

```sh
pixi run -e bun bunx backlog.md <command>
```

Install the locked Bun workspace first if dependencies are missing:

```sh
pixi run -e bun install-js
```

The current backlog is initialized at `backlog/config.yml` in filesystem-only mode. If the directory is absent in a fresh checkout, initialize it without Git integration:

```sh
pixi run -e bun bunx backlog.md init "QGIS SDK Workspace" --no-git --defaults --integration-mode none --backlog-dir backlog
```

## Non-interactive use

Read commands can launch an interactive UI. In an agent or CI shell, always use `--plain` for reads and `--json` when parsing output. Avoid bare `board`, `browser`, or task-detail commands without a non-interactive flag.

```sh
pixi run -e bun bunx backlog.md task list -s "To Do" --plain
pixi run -e bun bunx backlog.md search "<query>" --plain
pixi run -e bun bunx backlog.md task <id> --plain
```

## Task workflow

1. Read the task and its acceptance criteria before implementation.
2. When work is approved, claim and plan it using `task edit`; record progress in notes rather than comments.
3. Verify each acceptance criterion with evidence. Do not mark an unproven criterion complete.
4. Close a completed task with the CLI and include a concise final summary. Archive cancelled or duplicate work rather than deleting its history.
5. After a merge, update task status only when the merge and required validation are confirmed.

Create tasks with the CLI, for example:

```sh
pixi run -e bun bunx backlog.md task create "Title" -d "Description" --ac "First,Second" -l area --priority high
```

For command syntax, use `pixi run -e bun bunx backlog.md <command> --help` and consult [`REFERENCE.md`](REFERENCE.md).

## Shell quoting

- Quote arguments containing literal backticks to prevent command substitution.
- For multi-line notes, pass actual newlines or append one line at a time; do not use shell-specific `$'...'` quoting.
- Use comments only for review discussion; use notes and final summaries for execution progress.
