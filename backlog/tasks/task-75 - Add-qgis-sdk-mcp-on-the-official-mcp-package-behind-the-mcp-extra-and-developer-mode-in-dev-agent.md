---
id: TASK-75
title: >-
  Add qgis-sdk mcp on the official mcp package behind the [mcp] extra, and
  developer mode in dev --agent
status: To Do
assignee: []
created_date: '2026-10-26T09:48:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-74
type: enhancement
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-49 points 2 and 3. qgis-sdk-tools[mcp] extra pinning a tested range of the mcp package (never in the core dependency set, never in the runtime). qgis-sdk mcp (--project . | --connect URL --token-file PATH) is a stdio MCP server: it reads the plugin description over the endpoint and maps actions to tools with the action's JSON schema and readOnlyHint/destructiveHint, streams to handle-returning tools with progress notifications or subscribable resources, granted host operations to tools, description and project layers to resources, QgisSdk codes to structured tool errors; it reconnects after a QGIS restart or reload and fails in-flight calls as host-went-away without retrying. qgis-sdk dev --agent starts the endpoint in the dev host with the project's grants plus the dev profile, registers the dev.* namespace (reload, check, test, logs, describe, project tree read) through register_agent_tools, writes .qgis-sdk/dev/agent.json and prints the client config line.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Against the Python fakes and a scripted MCP client, tools/list reflects the description and the grants, tools/call validates inputs through the dispatcher, a stream reports progress, an ungranted operation is a structured error, and a dropped endpoint produces host-went-away with no retry (pure tests; mcp extra installed in the test env).
- [ ] #2 qgis-sdk mcp is absent and explained when the extra is missing (exit 2 with the pip line); the tools import boundary still holds (no Qt, no qgis); typer pin unchanged; the extra's range is checked by tests/scripts like the other pins.
- [ ] #3 dev --agent under a real QGIS exposes the dev.* namespace, dev.reload round-trips a source edit and the agent sees the new tools list (devtools harness, QGIS_SDK_DEVTOOLS=1); doc-12 documents developer mode with the client config for the common clients.
<!-- AC:END -->
