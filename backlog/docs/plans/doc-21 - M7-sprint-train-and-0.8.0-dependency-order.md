---
id: doc-21
title: M7 sprint train and 0.8.0 dependency order
type: guide
created_date: '2026-10-26 09:55'
---
# M7 sprint train and 0.8.0 dependency order

**Status:** Planning. This document orders work the m-7 tasks already
declare; it adds no scope. Sprint membership lives here and in the milestone
body, not in task fields ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

**Baseline:** measured at the start of sprint 1 and recorded here.

## 1. Where m-7 starts from

Expected from 0.6.0: the generated host (`host()`, grants in pyproject,
`register_host_operations(only=)`) and the generated schema module. Expected
from 0.7.0: the standard surfaces and `LogPanel`, the console session
(decision-48). What is missing, and what this milestone adds ([decision-49](../../decisions/decision-49%20-%20Expose-the-runtime-to-agents-over-a-loopback-transport-with-the-MCP-server-in-the-tools-for-developers-and-users-alike.md)):

| Gap | Owner |
| --- | --- |
| The dispatcher has one transport, `QWebChannel`; nothing outside the page can call an action | **TASK-74** |
| No MCP anywhere; an agent helping develop a plugin has no tool surface | **TASK-75** |
| An installed plugin has no way to let its user's agent in, and no consent model | **TASK-76** |
| An agent cannot see or drive a native surface; authors have no snapshot test for Qt UI (decision-51) | **TASK-79** |

## 2. Dependency read of the m-7 tasks

| Task | Declared dependencies | Needs | Startable |
| --- | --- | --- | --- |
| [TASK-74](../../tasks/task-74%20-%20Add-the-loopback-agent-transport-to-the-runtime-with-per-session-authority-and-the-AGENT-check-rules.md) loopback transport + AGENT rules | TASK-64, TASK-66 | 0.6.0 only | after 0.6.0 |
| [TASK-75](../../tasks/task-75%20-%20Add-qgis-sdk-mcp-on-the-official-mcp-package-behind-the-mcp-extra-and-developer-mode-in-dev-agent.md) `qgis-sdk mcp` + developer mode | TASK-74 | 0.6.0 only | after 74 |
| [TASK-76](../../tasks/task-76%20-%20Add-user-mode-tool.qgis-sdk.agent-the-generated-Agent-access-surface-consent-audit-and-the-uvx-client-config.md) user mode | TASK-75, TASK-68 | 0.7.0 surfaces | after 0.7.0 |
| [TASK-79](../../tasks/task-79%20-%20Add-UI-snapshots-structured-tree-plus-screenshot-of-the-plugins-surfaces-dev.ui-agent-tools-and-the-ui_snapshot-fixture.md) UI snapshots + `dev.ui` | TASK-75, TASK-68 | 0.7.0 surfaces | after 75 |
| [TASK-78](../../tasks/task-78%20-%20Prepare-and-qualify-0.8.0-release.md) 0.8.0 gate | TASK-32, 74, 75, 76, 79 | — | release gate |

## 3. Sprint train

- **Sprint 1: TASK-74.** `qgis_sdk.agent`: host-busy deadline and the one-at-a-time re-entrancy guard (AC 4–5), stdlib `http.server` thread on
  `127.0.0.1`, token file, `Origin` check, one `ViewBinding` per session,
  GUI-thread handoff through the scheduler, SSE for stream frames; the
  bridge test vectors re-run over it; `[tool.qgis-sdk.agent]` parsing and
  the AGENT001–003 rules in `check`. No new dependency, no bridge change.
- **Sprint 2: TASK-75.** The `[mcp]` extra on a tested range of the `mcp`
  package; `qgis-sdk mcp` with the description→tools mapping, progress,
  resources, structured errors, reconnect; `dev --agent`, the `dev.*`
  namespace through `register_agent_tools`, `.qgis-sdk/dev/agent.json` and
  the printed client config; the scripted MCP client in the test support.
  After this sprint the developer loop works, whatever 0.7.0's state is.
- **Sprint 3: TASK-76.** `enabled`/`actions`/`grants`/annotations baked by
  `build`; the Agent access surface and menu binding rendered only when
  enabled; consent list, ask-each-time, URL, Copy client config (`uvx` and
  `pipx` forms), Rotate token, indicator, `LogPanel` audit, first-connection
  notice; the build-install harness proving a disabled plugin has no
  listening code; the `uvx` route rehearsed once against an index and
  recorded in doc-14. **TASK-79** rides as a second series: the snapshot
  module with the role table and stable ids, `dev.ui.*`, the `ui_snapshot`
  fixture and the CLI capture.
- **Gate: TASK-78.** Python-only release `python-v0.8.0`; the zero bridge
  delta shown, not assumed. Only on an explicit "Release 0.8.0".

## 4. Hygiene to do at sprint start

- Re-measure the baseline.
- If the owner wants the developer loop before 0.7.0 ships, sprints 1 and
  2 run between m-5 and m-6 as 0.6.x work *without* changing the 0.8.0
  number; the m-7 body's sprint train is amended, not this history.
- Point 5 of decision-49 (native MCP in the runtime) stays unbuilt unless a
  client that cannot launch `uvx` is named.
