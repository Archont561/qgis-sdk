---
title: For coding agents
description: What an agent needs to write, check, test and build a QGIS SDK plugin without guessing - the command set, the loop, and a copyable AGENTS.md block.
---

An agent that knows four commands can carry a QGIS SDK plugin from an empty
directory to an installable ZIP: `new`, `check`, `test`, `build`. Everything it
must not do is what `check` refuses.

## The loop

1. **Scaffold.** `qgis-sdk new my_tools --title "My tools" --no-input` writes a
   plugin that already passes `check`.
2. **Declare.** Actions, surfaces and providers are decorators in
   `my_tools/plugin.py`. Handlers take `ctx` first and their inputs after it.
3. **Check.** `qgis-sdk check --json` reports codes, not prose. Fix every code
   before writing anything else; `UI003` in particular means an action cannot be
   placed on a button because it takes inputs.
4. **Test.** `qgis-sdk test` runs the pure suite with the kit's fakes, so it
   needs no QGIS. `--target qgis` is a separate, optional run.
5. **Build.** `qgis-sdk build` writes `dist/<name>-<version>.zip` with the
   rendered `metadata.txt` and the vendored runtime.

[Project checks](/python/project-checks/) - every code and what it refuses.
[CLI MCP server](/guides/cli-mcp/) - the same commands as MCP tools.

## Giving your agent the SDK

Paste this into your plugin repository's `AGENTS.md`. It is short on purpose:
the commands are stable, and the rest the agent should read from `qgis-sdk
check` rather than from prose.

```text
This repo is a QGIS SDK plugin. Commands: qgis-sdk check | test | dev | build.
Run `qgis-sdk check` before finishing any task and fix every code it reports.
Declarations live in the package's plugin.py; never edit generated/ or dist/ by hand.
qgis-sdk test runs without QGIS - keep it that way; --target qgis needs a host.
```

## Via MCP, if the client prefers tools to a shell

```sh
pip install 'qgis-sdk[mcp]'
```

then start `qgis-sdk` with `["mcp", "--project", "/absolute/path/to/workspace"]`
over stdio. The server exposes `qgis_sdk_new`, `qgis_sdk_bridge_generate`,
`qgis_sdk_processing_generate`, `qgis_sdk_check`, `qgis_sdk_build`,
`qgis_sdk_test`, `qgis_sdk_run`, `qgis_sdk_dev`, `qgis_sdk_targets` and the five
`qgis_sdk_ui_*` surface tools. A nonzero `exit_code` is a CLI failure even when
the MCP call itself succeeded.

## What the agent must not assume

- **It is not a sandbox.** Generators, tests and builds execute project code
  with the user's permissions; approve consequential calls.
- **`metadata.txt` is output.** Editing it changes nothing in the ZIP.
- **`iface` does not exist.** Handlers read `ctx`; anything the host owns is a
  service there.
- **Desktop is not Server.** `hosts` decides which hosts a class runs on, and a
  QGIS built without Server refuses the server host by name.

## This repository's own agent file

`AGENTS.md` here is generated, not written: `bun run agents` refreshes the
regions `@eugeniughelbur/agents-md` owns, and `bun run agents:check` fails in CI
when someone edited a generated region by hand. The same split - generated
regions, human prose around them - is what keeps an agent file honest over time.
