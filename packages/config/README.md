# @workspace/config

**The TypeScript and Bunup configuration every package in this workspace
extends.**

A private workspace package: strict shared `tsconfig` defaults, a library
variant with declarations and an app variant for browser pages, and the
Bunup preset the published packages build with (ESM, declarations, clean
output, sourcemaps).

> Status: private, never published; versioned with the workspace.

## Installation

```json
{ "devDependencies": { "@workspace/config": "workspace:*" } }
```

## Example

```json
{ "extends": "@workspace/config/tsconfig/library.json" }
```

```ts
import { bunupPreset } from "@workspace/config/bunup";
export default { ...bunupPreset, entry: ["src/index.ts"] };
```

`@workspace/config/tsconfig/base.json` holds the shared defaults,
`library.json` the declaration settings, `app.json` the browser settings.

## Documentation

- [Workspace, harnesses and qualification evidence](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md) -
  environments, the Pixi and Bun tasks and the repository layout.

## License

MIT
