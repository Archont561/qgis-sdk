---
title: CLI MCP server
description: Use the SDK's developer commands from an MCP client.
---

The optional CLI MCP server runs independently of QGIS and the plugin HTTP
runtime. It exposes development commands only; it never connects to a running
plugin. Install the extra in the Python environment used by your MCP client:

```sh
pip install 'qgis-sdk[mcp]'
```

Configure the client to start `qgis-sdk` with the arguments
`["mcp", "--project", "/absolute/path/to/workspace"]` using **stdio** transport.
For example, clients accepting an `mcpServers` JSON object can use:

```json
{
  "mcpServers": {
    "qgis-sdk": {
      "command": "qgis-sdk",
      "args": ["mcp", "--project", "/absolute/path/to/workspace"]
    }
  }
}
```

Use an absolute path to the installed `qgis-sdk` executable if your client does
not inherit its Python environment's PATH. `--project` defaults to the server's
current directory and must name an existing directory; it need not yet be a
plugin. The MCP dependency is imported only when this command runs. If it is
missing, the command exits with an installation instruction; other commands do
not require it.

## Tools and results

The server exposes `qgis_sdk_new`, `qgis_sdk_scaffold` (deprecated alias),
`qgis_sdk_bridge_generate`, `qgis_sdk_processing_generate`, `qgis_sdk_check`,
`qgis_sdk_build`, `qgis_sdk_test`, `qgis_sdk_run`, `qgis_sdk_dev`,
`qgis_sdk_targets`, and the
surface tools `qgis_sdk_ui_list`, `qgis_sdk_ui_open`, `qgis_sdk_ui_snapshot`,
`qgis_sdk_ui_act` and `qgis_sdk_ui_diff`. The surface tools start QGIS: they
open the plugin's own surfaces from a generated host and capture what the host
opened. `qgis_sdk_ui_act` is developer-only — it drives a surface with
synthetic input, which a plugin's runtime never does and never offers.
Pass `args` as an array of individual CLI argument strings, e.g.
`{"args": ["--json"]}` to `qgis_sdk_targets` or
`{"args": ["my-plugin", "--no-input"]}` to `qgis_sdk_new`. Pass
`["--help"]` to discover each command's complete options (for `dev`, read the
output with `qgis_sdk_dev_status`). There is no shell expansion or interactive
input, and `qgis_sdk_run` blocks until the app quits: pass `--once` when a call
has to return. QGIS is required only for commands or targets
that already require it.

Most calls return `exit_code`, `stdout`, `stderr`, `timed_out`, and `truncated`.
A nonzero exit code is a CLI failure even if the MCP call itself succeeded.
Each output stream keeps its most recent 256 KiB, and calls are stopped after
300 seconds; when `truncated` is true the beginning of that stream was dropped,
because the end is what diagnoses a failure.
`qgis_sdk_dev` starts a long-running session and returns a `session_id`;
`qgis_sdk_dev_status` reads its recent output and `qgis_sdk_dev_stop` stops and
forgets it. The server attempts to stop sessions during orderly shutdown;
an abrupt termination or independently detached descendants can leave processes
running. On Windows, stopping the command does not guarantee that every descendant
process exits. Check and close any remaining QGIS or web-server processes. Up to eight dev
sessions may be retained; stop completed sessions to free their slots.

## Trust and limitations

**This is not a sandbox.** The project directory is only a working directory,
not a filesystem boundary. Tools run with the user's environment and full
filesystem and network permissions. Generators, tests, builds and development
sessions can execute project code; scaffolding and generation can write or
replace files, and installation options can execute package managers. Only
connect trusted clients and approve consequential tool calls in the client.
The CLI server does not adapt the plugin REST API or expose the `plugin` client
commands as MCP tools. Plugin HTTP access is a separate interface.
