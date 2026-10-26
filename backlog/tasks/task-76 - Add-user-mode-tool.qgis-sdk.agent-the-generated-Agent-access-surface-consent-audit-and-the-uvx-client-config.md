---
id: TASK-76
title: >-
  Add user mode: [tool.qgis-sdk.agent], the generated Agent access surface,
  consent, audit and the uvx client config
status: To Do
assignee: []
created_date: '2026-10-26T09:48:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-75
  - TASK-68
type: enhancement
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-49 point 4. [tool.qgis-sdk.agent] enabled/actions/grants/annotations baked by build; build renders the Agent access standard surface bound to the plugin menu only when enabled: off by default per plugin and profile, consent list (author allowlist intersected with user ticks, destructive tools optionally ask each time), URL, Copy client config (uvx --from 'qgis-sdk-tools[mcp]' qgis-sdk mcp --connect ... --token-file ..., and the pipx form), Rotate token, active-session indicator, every call in the LogPanel, message-bar notice on first connection. One endpoint per plugin. A plugin without enabled = true carries no listening code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A built plugin with enabled = true installs from ZIP into a real QGIS, the surface opens from the menu, the endpoint starts only after the user enables it, a scripted MCP client sees exactly the ticked tools, an ask-each-time tool blocks until confirmed, and rotating the token invalidates the running session (build-install harness, QGIS_SDK_BUILD_INSTALL=1).
- [ ] #2 A plugin without enabled = true contains no qgis_sdk.agent server code in the ZIP and opens no socket (archive inspection + native test); the vendored runtime manifest still declares no dependencies.
- [ ] #3 The copied config launches the published tools server without touching QGIS's Python (documented, rehearsed once against a TestPyPI or local index and recorded in doc-14); doc-12 documents user mode, the consent model and what the agent can never do.
<!-- AC:END -->
