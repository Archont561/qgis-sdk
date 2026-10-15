# Backlog.md — command reference

Disclosed reference for the [`backlog`](SKILL.md) skill. In this repo every command runs as `pixi run backlog <args>`. Trust `pixi run backlog <command> --help` as the authoritative surface — this table is a convenience cache and can lag the installed version.

## Top-level commands

| Command | Purpose |
|---|---|
| `init [projectName]` | Initialize a backlog in the repo (scaffolds `backlog/`, chooses AI integration: MCP / CLI / skip) |
| `task \| tasks` | Create, list, view, edit tasks |
| `draft` | Draft workflow (create / promote / demote) |
| `board` | Terminal Kanban board (interactive; `board export` for markdown) |
| `doc` | Project documents |
| `decision` | Decision records |
| `agents` | Manage agent instruction files |
| `config` | Read/write config |
| `cleanup` | Move completed tasks to the completed folder by age |
| `browser` | Web UI (default port 6420) |
| `overview` | Project statistics and metrics |
| `search` | Fuzzy search across tasks, docs, decisions |

## Task creation

| Action | Example |
|---|---|
| Create | `task create "Add OAuth System"` |
| Description | `task create "Feature" -d "Add auth system"` |
| Assignee | `task create "Feature" -a @sara` |
| Status | `task create "Feature" -s "In Progress"` |
| Labels | `task create "Feature" -l auth,backend` |
| Priority | `task create "Feature" --priority high` |
| Plan | `task create "Feature" --plan "1. Research\n2. Implement"` |
| Acceptance criteria | `task create "Feature" --ac "Must work,Must be tested"` |
| DoD items | `task create "Feature" --dod "Run tests"` |
| No default DoD | `task create "Feature" --no-dod-defaults` |
| Notes | `task create "Feature" --notes "Started research"` |
| Final summary | `task create "Feature" --final-summary "Completion summary"` |
| Dependencies | `task create "Feature" --dep task-1,task-2` |
| Refs / docs | `task create "Feature" --ref src/api.ts --doc docs/spec.md` |
| Sub-task | `task create -p 14 "Add Login with Google"` |
| Draft | `task create "Feature" --draft` |

## Task listing & viewing

| Action | Example |
|---|---|
| List | `task list [-s <status>] [-a <assignee>] [-p <parent>] [--labels <l>] [--search <q>] [--limit <n>]` |
| List (AI) | `task list -s "To Do" --plain` |
| List (JSON) | `task list --status "To Do" --json` |
| Watch JSON | `task list --json --watch` (initial full list, then changed full replacements) |
| By parent | `task list --parent 42` or `task list -p task-42` |
| View detail | `task 7` (interactive; press `E` to edit) |
| View (AI) | `task 7 --plain` |
| View (JSON) | `task 7 --json` |

## Task editing

| Action | Example |
|---|---|
| Edit fields | `task edit 7 -a @sara -l auth,backend -s "In Progress" --priority high` |
| Plan | `task edit 7 --plan "Implementation approach"` |
| Add AC | `task edit 7 --ac "New criterion" --ac "Another"` |
| Remove AC | `task edit 7 --remove-ac 2` |
| Check / uncheck AC | `task edit 7 --check-ac 1 --uncheck-ac 3` |
| Add DoD | `task edit 7 --dod "Ship notes"` |
| Check / uncheck / remove DoD | `task edit 7 --check-dod 1 --uncheck-dod 2 --remove-dod 4` |
| Notes (replace) | `task edit 7 --notes "Completed X, working on Y"` |
| Append notes | `task edit 7 --append-notes "New findings"` |
| Final summary | `task edit 7 --final-summary "..."` / `--append-final-summary "..."` / `--clear-final-summary` |
| Comment | `task edit 7 --comment "Question for review" --comment-author @sara` |
| Dependencies | `task edit 7 --dep task-1 --dep task-2` |
| Archive | `task archive 7` |
| Complete | `task complete 7` (cleanup: off the board, record + deps preserved) |

## Drafts & dependencies

| Action | Example |
|---|---|
| Draft create → promote | `draft create "Spike GraphQL"` → `draft promote 3.1` |
| Demote to draft | `task demote <id>` |
| Add deps | `task edit 7 --dep task-1,task-5,task-9` |
| Find by modified file | `search --modified-file src/path.ts --plain` |

## Board, search, config

| Action | Example |
|---|---|
| Kanban board | `board` (interactive) |
| Export board | `board export` (shareable markdown) |
| Web UI | `browser` (port 6420) — `browser --port 8080 --no-open` |
| Search | `search "kanban"` / `search "auth" --json` |
| Set config | `config set defaultEditor "code --wait"` |
| List config | `config list` |

Common config keys: `default_assignee`, `default_status` (default `To Do`), `statuses` (`[To Do, In Progress, Done]`), `date_format`, `default_editor`, `default_port` (`6420`), `auto_open_browser`.

## Storage layout

Tasks live under a project-local backlog folder (`backlog/`, `.backlog/`, or a `backlog_directory` set in `backlog.config.yml`). Each task is `task-<id> - <title>.md` (e.g. `task-12 - Fix typo.md`) with YAML front-matter metadata. Sub-tasks nest their id (`task-1.1`). Structure: `backlog/{tasks,drafts,docs,decisions,completed,archive,config.yml}`.

## Stable JSON examples

```
pixi run backlog task list --status "To Do" --json | jq '.tasks[] | .id'
pixi run backlog task view <id> --json | jq '.task.acceptanceCriteria'
pixi run backlog search "authentication" --json | jq '.results[] | [.type, .data.id]'
```

## Sources

- Backlog.md README & CLI-INSTRUCTIONS — https://github.com/MrLesk/Backlog.md
