# Concepts

Explanations of the domain: what the things called by the guides actually are,
and why they are shaped that way. Definitions live on the site, once each.

## Vocabulary

[Concepts and vocabulary](https://archont561.github.io/qgis-sdk/start/concepts/)
is the canonical glossary: plugin, action, surface, `ctx`, services, grants,
bridge, scope. Start there before reading a reference page.

## The areas it names

| Area | Where it is explained |
| :-- | :-- |
| Declarations: actions, inputs, outputs | [Declarations](https://archont561.github.io/qgis-sdk/python/declarations/) |
| The contract layer that keeps plugin logic QGIS-free | [Pure contract layer](https://archont561.github.io/qgis-sdk/python/pure-contract-layer/) |
| Runtime scope: what a plugin may touch | [Scoped plugin runtime](https://archont561.github.io/qgis-sdk/python/scoped-plugin-runtime/) |
| The desktop host and the project manifest | [Desktop host](https://archont561.github.io/qgis-sdk/python/desktop-host-host-and-the-project-manifest/) |
| Surfaces: forms, native bindings, web views | [Forms](https://archont561.github.io/qgis-sdk/python/forms-an-actions-inputs-as-a-window/), [desktop bindings](https://archont561.github.io/qgis-sdk/python/desktop-bindings-and-native-surfaces/) |
| The Python-to-web bridge | [WebEngine bridge, host side](https://archont561.github.io/qgis-sdk/python/webengine-bridge-host-side/) |
| Jobs, grants and the HTTP allowlist | [Scoped jobs](https://archont561.github.io/qgis-sdk/python/scoped-jobs/), [grants, the console and the allowlist](https://archont561.github.io/qgis-sdk/python/grants-the-console-and-the-http-allowlist/) |
| Processing: algorithms, providers, safe outputs | [Processing algorithms](https://archont561.github.io/qgis-sdk/python/processing-algorithms-and-safe-outputs/), [providers](https://archont561.github.io/qgis-sdk/python/providers-algorithms-in-the-qgis-processing-toolbox/) |
| The typed TypeScript client of the same contract | [TypeScript SDK](https://archont561.github.io/qgis-sdk/typescript/) |

## Sources

- `apps/docs/content/docs/start/concepts.md` - the glossary.
- `apps/docs/guides/doc-12 - qgis-sdk-Python-package-guide.md` - the opening sections of the Python guide explain each area.
- `backlog/decisions/` - why an area is shaped the way it is; the [design decisions table](https://archont561.github.io/qgis-sdk/reference/design-decisions/) lists all of them.
