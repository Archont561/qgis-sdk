---
id: TASK-75
title: >-
  Add qgis-sdk mcp on the official mcp package behind the [mcp] extra
status: In Progress
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
Provide a standalone stdio MCP server for the developer CLI behind the optional qgis-sdk[mcp] extra. The runtime does not implement MCP and the CLI MCP server does not adapt the plugin REST endpoint. External plugin calls and streams use a separate tools-side HTTP client and CLI. The runtime agent module and `dev --agent` were removed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A scripted MCP client can discover and invoke the supported developer CLI commands over stdio; the server does not expose a runtime MCP adapter.
- [ ] #2 qgis-sdk mcp lazily checks the optional package and explains a missing extra (exit 2 with the pip line); tools import without Qt or QGIS; typer pin is unchanged and the extra is checked.
- [ ] #3 The CLI MCP server's process lifecycle, side effects, limits and client configuration are documented and qualified across supported platforms.
<!-- AC:END -->

## Implementation notes

The standalone CLI-first slice exposes developer CLI commands over stdio with an
optional `qgis-sdk[mcp]` install. It does not connect to the plugin REST
endpoint or implement `dev --agent`. The experimental runtime agent API was
removed, and plugin REST commands are deliberately absent from the MCP
inventory.
