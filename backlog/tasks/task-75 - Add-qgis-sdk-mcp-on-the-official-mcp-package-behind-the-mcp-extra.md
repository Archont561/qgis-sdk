---
id: TASK-75
title: 'Add qgis-sdk mcp on the official mcp package behind the [mcp] extra'
status: Done
assignee: []
created_date: '2026-10-26T09:48:00Z'
updated_date: '2026-10-29 13:34'
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
- [x] #1 A scripted MCP client can discover and invoke the supported developer CLI commands over stdio; the server does not expose a runtime MCP adapter.
- [x] #2 qgis-sdk mcp lazily checks the optional package and explains a missing extra (exit 2 with the pip line); tools import without Qt or QGIS; typer pin is unchanged and the extra is checked.
- [x] #3 The CLI MCP server's process lifecycle, side effects, limits and client configuration are documented and qualified across supported platforms.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The standalone CLI-first slice exposes developer CLI commands over stdio with an
optional `qgis-sdk[mcp]` install. It does not connect to the plugin REST
endpoint or implement `dev --agent`. The experimental runtime agent API was
removed, and plugin REST commands are deliberately absent from the MCP
inventory.

Closed 2026-10-29. AC1: test_stdio_server_exposes_and_runs_cli_commands drives the real server over stdio with an mcp ClientSession, lists the tool inventory and invokes commands; the inventory is asserted against the Typer command tree minus mcp/plugin, so no runtime adapter and no plugin REST surface. AC2: a missing extra exits 2 with the qgis-sdk[mcp] line (test_mcp_command_without_optional_dependency_explains_installation); importing the CLI does not import mcp; the tools declare mcp==2.3.0 only as an optional extra, the kit forwards it, and typer stays pinned at 0.27.3. AC3: guides/cli-mcp.md documents installation, client configuration, the tool inventory, output limits (256 KiB per stream, 300 s, eight dev sessions), shutdown caveats and the trust limits; the CLI suite passes on Linux, macOS and Windows CI, which install [dev] including mcp, so the stdio integration runs there rather than skipping.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Standalone stdio MCP server for the developer CLI behind the optional qgis-sdk[mcp] extra. The dependency is imported only by the mcp command; the server exposes the developer commands only, never adapts the plugin REST endpoint, and plugin REST commands are deliberately absent from the inventory. Verified in an isolated venv (4 passed, including a real stdio client) and on Linux/macOS/Windows CI.
<!-- SECTION:FINAL_SUMMARY:END -->
