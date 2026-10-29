---
id: doc-21
title: M7 sprint train and 0.8.0 dependency order
type: guide
created_date: '2026-10-26 09:55'
---
# M7 sprint train and 0.8.0 dependency order

**Status:** Sprints 1 and 2 delivered on 2026-10-29 (PR #135, merge
`2c0930b`); TASK-79, TASK-73, TASK-77 and the TASK-78 gate remain. This
document orders work the m-7 tasks already declare; it adds no scope. Sprint
membership lives here and in the milestone body, not in task fields
([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

**Baseline:** measured at the start of sprint 1 and recorded here.

## 1. Where m-7 starts from

Expected from 0.6.0: the generated host (`host()`, grants in pyproject,
`register_host_operations(only=)`) and the generated schema module. Expected
from 0.7.0: the catalogue and `LogView`, the console session
(decision-48). What is missing, and what this milestone adds (decision-49 is superseded; TASK-74 now covers the plugin HTTP API):

| Gap | Owner |
| --- | --- |
| The dispatcher has one transport, `QWebChannel`; nothing outside the page can call an action | **TASK-74** |
| No MCP anywhere; an agent helping develop a plugin has no tool surface | **TASK-75** |
| An installed plugin cannot be called from outside QGIS without an MCP client | **TASK-74** (REST + tools clients) |
| An agent cannot see or drive a native surface; authors have no snapshot test for Qt UI (decision-51) | **TASK-79** |

## 2. Dependency read of the m-7 tasks

| Task | Declared dependencies | Needs | Startable |
| --- | --- | --- | --- |
| [TASK-74](../../tasks/task-74%20-%20Expose-opted-in-plugin-actions-and-streams-over-an-explicitly-hosted-loopback-REST-API.md) loopback REST API + tools clients | TASK-64, TASK-66 | 0.6.0 only | after 0.6.0 |
| [TASK-75](../../tasks/task-75%20-%20Add-qgis-sdk-mcp-on-the-official-mcp-package-behind-the-mcp-extra.md) `qgis-sdk mcp` + developer mode | TASK-74 | 0.6.0 only | after 74 |
| [TASK-79](../../tasks/task-79%20-%20Add-UI-snapshots-structured-tree-plus-screenshot-of-the-plugins-surfaces-dev.ui-agent-tools-and-the-ui_snapshot-fixture.md) UI snapshots + `dev.ui` | TASK-75, TASK-68 | 0.7.0 surfaces | after 75 |
| [TASK-78](../../tasks/task-78%20-%20Prepare-and-qualify-0.8.0-release.md) 0.8.0 gate | TASK-32, 74, 75, 79 | — | release gate |

## 3. Sprint train

- **Sprint 1: TASK-74 — delivered** (PR #135, merge `2c0930b`; audit
  follow-ups TASK-143–148 fixed in the same pull request). `qgis_sdk.http`:
  explicitly started stdlib `http.server` on `127.0.0.1`, a private token
  file, `Host`/`Origin` checks, allowlisted discovery, actions and SSE
  streams, a host-busy deadline and the one-at-a-time re-entrancy guard; every
  dispatch on the QGIS owner thread.
  Clients live in `qgis-sdk-tools` (`plugin describe|call|stream` and the
  Python `PluginClient`). No new runtime dependency, no bridge change, and
  no plugin REST through MCP.
- **Sprint 2: TASK-75 — delivered** (same pull request). The `[mcp]` extra
  on a tested range of the `mcp` package; `qgis-sdk mcp` exposing the
  developer CLI commands over stdio, lazily loaded with an availability
  check, structured output limits and managed dev sessions. Plugin REST
  commands are explicitly excluded.
  **TASK-79 — open, next in the train** — rides as a second series: the
  snapshot module with the role table and stable ids, `dev.ui.*`, the
  `ui_snapshot` fixture and the CLI capture.
- **Sprint 3: TASK-73 and TASK-77 — open.** The console session reuses the
  curated services the HTTP API already reaches; TASK-73's AC 2 names the
  `QGIS_SDK_DESKTOP_ADAPTER` harness, which the smoke suite replaced, so that
  criterion is re-worded before implementation. TASK-77 has no dependents and
  slots in anywhere before the gate.
- **Gate: TASK-78 — open, blocked on TASK-73, TASK-77 and TASK-79.**
  Python-only release `python-v0.8.0`; the zero bridge delta shown, not
  assumed. Only on an explicit "Release 0.8.0".

## 4. Hygiene to do at sprint start

- Re-measure the baseline.
- If the owner wants the developer loop before 0.7.0 ships, sprints 1 and
  2 run between m-5 and m-6 as 0.6.x work *without* changing the 0.8.0
  number; the m-7 body's sprint train is amended, not this history.
- Point 5 of decision-49 (native MCP in the runtime) stays unbuilt unless a
  client that cannot launch `uvx` is named.

## 5. Tasks re-scoped in from m-6 (2026-10-27)

TASK-73 (`qgis_sdk.console`, decision-48) and TASK-77 (externals with a
startup probe and pure-Python vendoring, decision-50) arrive from m-6
unopened ([doc-19](doc-19%20-%20M6-sprint-train-and-0.7.0-dependency-order.md) section 5). Placement:

| Task | Depends on | Language | Where in the train |
| --- | --- | --- | --- |
| TASK-73 console session | TASK-63, TASK-64 (Done) | Python | with sprint 2: the console and the plugin HTTP API reach the same curated services, and TASK-75's CLI tests reuse the console harness |
| TASK-77 externals and vendoring | TASK-64 (Done) | Python (tools) | its own small pull request anywhere before the TASK-78 gate; nothing in m-7 depends on it |

Neither changes `packages/qgis-sdk-typescript`, so m-7's "no bridge
release" statement stands. TASK-78's dependencies and AC evidence now
include both.

## 6. Authoring spike added to the gate (2026-10-28)

[TASK-140](../../tasks/task-140%20-%20Spike-a-FastAPI-style-plugin-application-and-action-groups-for-0.8.0.md)
is a further TASK-78 dependency. It evaluates an additive FastAPI-style plugin
application and action groups for 0.8.0; it does not itself approve or deliver
implementation. If implementation is approved for this release, the gate must
revisit the expected unchanged bridge and qualify compatibility and migration.
The worker-first named jobs refactor remains targeted to 0.9.0.
