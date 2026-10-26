---
id: decision-49
title: Expose the runtime to agents over a loopback transport with the MCP server in the tools for developers and users alike
date: '2026-10-26'
status: accepted
---
## Context

The owner wants agents (MCP clients such as Claude Code, Claude Desktop,
Cursor) to call a plugin's actions and the curated services, in two modes:
a **developer mode** where the plugin author's agent drives the plugin under
`qgis-sdk dev`, and a **user mode** where an installed plugin lets the end
user's agent drive it. The bridge already has the seam: `ChannelTransport`
("text in, dispatcher, text out", no Qt) carries versioned envelopes for any
channel that moves strings, the `Dispatcher` owns authority and ordering per
`ViewBinding`, and `register_host_operations(only=)` scopes the curated
services by grant (decisions 9, 23, 27, 43).

Two constraints shape where the MCP protocol itself may live. The runtime is
vendored into every built plugin and has **no dependencies** (decision-35),
and the official `mcp` package (2.3.0) pulls pydantic (compiled
`pydantic-core`), starlette, uvicorn, httpx, `pyjwt[crypto]` (compiled
`cryptography`), opentelemetry and more - unvendorable and far too heavy for a
plugin ZIP. The tools, by contrast, are an ordinary pip-installed CLI whose
core pins only `typer`.

## Decision

1. **The runtime speaks envelopes, not MCP.** `qgis_sdk.agent` adds a
   loopback transport: a stdlib `http.server` thread bound to `127.0.0.1`
   only, bearer token from a 0600 file, `Origin` checked, each MCP session
   mapped to one `ViewBinding`, every request handed to the GUI thread
   through the existing scheduler (decision-21) and dispatched through
   `ChannelTransport`; stream frames go out as server-sent events. Same
   envelopes, same `BRIDGE_PROTOCOL_VERSION`, same authority, same
   `HOST_FINGERPRINT`; the bridge test vectors test this transport too. The
   runtime never binds a non-loopback address and never implements `eval`.
2. **The MCP server lives in the tools, behind an extra.** `qgis-sdk mcp`
   is a stdio MCP server built on the official `mcp` package, installed as
   `qgis-sdk-tools[mcp]` so the core CLI keeps its single pinned
   dependency. It connects to a runtime endpoint, reads the plugin
   description over it and maps: action → tool (the action's JSON schema as
   `inputSchema`, `readOnlyHint`/`destructiveHint` from the author's
   annotation); stream → tool returning a handle plus progress
   notifications, or a subscribable resource for jobs; granted host
   operation → tool; `qgis://plugin/description` and `qgis://project/layers`
   → resources; `QgisSdk*` codes → structured tool errors, never tracebacks.
   It reconnects after a QGIS restart or plugin reload and fails in-flight
   calls as "host went away" rather than retrying (decision-23).
3. **Developer mode.** `qgis-sdk dev --agent` starts the loopback endpoint
   in the dev host with the project's agent grants plus a dev profile, and
   registers a `dev.*` tool namespace through an extension point
   (`register_agent_tools`): `dev.reload`, `dev.check`, `dev.test`,
   `dev.logs`, `describe`, read access to the project tree. `dev` writes
   `.qgis-sdk/dev/agent.json` (URL, token path) and prints the one-line
   client config: `qgis-sdk mcp --project .`.
4. **User mode.** The author opts the plugin in with
   `[tool.qgis-sdk.agent] enabled = true`, `actions = [...]`, `grants =
   [...]` and per-action annotations, baked into the build. `build`
   renders an **Agent access** surface (decision-45/46 standard surface)
   bound to the plugin's menu: off by default per plugin and profile; a
   consent list (author allowlist ∩ user ticks; destructive tools may be
   set to "ask each time"); URL, **Copy client config** and **Rotate
   token** buttons; an indicator while a session is active; every call in
   the plugin's `LogPanel`; a message-bar notice on first connection. The
   copied config launches the same tools server without touching QGIS's
   Python: `uvx --from "qgis-sdk-tools[mcp]" qgis-sdk mcp --connect
   <url> --token-file <path>` (or the `pipx` equivalent). One endpoint per
   plugin; each vendored runtime stays independent. A plugin without
   `enabled = true` carries no listening code at all.
5. **Native MCP in the runtime is deferred, not refused.** If clients that
   speak streamable HTTP directly make the `uvx` hop unwelcome, a stdlib
   subset of MCP (initialize, tools, resources, progress) can be added to
   `qgis_sdk.agent` later behind the same mapping; it is not built until
   asked for, and it would never bring the `mcp` package into the runtime.
6. **Checks.** `AGENT001` an exposed action without a read-only/destructive
   annotation; `AGENT002` an unknown agent grant; `AGENT003` `enabled =
   true` without any exposed action. Mirrors of the web rules.

## Consequences

- Four clients of one surface and one authority model: page, handler,
  console (decision-48), agent. Nothing reaches the agent that the author
  did not declare and - in user mode - the user did not tick.
- `qgis-sdk-tools` grows an optional `mcp` extra pinned to a tested range
  of the `mcp` package; the core dependency set is unchanged. The runtime
  gains stdlib-only code and no dependency. The bridge is untouched.
- User mode requires `uv` or `pipx` on the user's machine, which agent
  users already have; the alternative (shipping MCP inside the plugin) is
  recorded as point 5.
- Scheduled as its own release, 0.8.0 (m-7, re-pointed), after the UI
  toolkit whose surfaces user mode needs; the deferred native-compute
  research moves to 0.9.0 (m-8; later to 1.1.0 as m-11 by decision-52). Tasks: TASK-74 (runtime transport and
  checks), TASK-75 (tools MCP server and developer mode), TASK-76 (user
  mode), gate TASK-78.
