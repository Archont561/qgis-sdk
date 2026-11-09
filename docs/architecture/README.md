# Architecture

How the system is put together, and the decisions that keep it that way. A
decision is a record, not a paragraph in a guide: it is written once in
`backlog/decisions/` with its status, and the site renders the table.

## Decision records

- [Design decisions](https://archont561.github.io/qgis-sdk/reference/design-decisions/) - every accepted decision in one table, regenerated from `backlog/decisions/` on each build.
- `backlog/decisions/decision-<n> - <title>.md` - the records themselves. `decision-73` is the current shape of the documentation site; `decision-29`, the landing page; `decision-1`, the declarative authoring API.

A record states the problem, the decision, the consequences and what was
rejected, so a later reader can tell whether the reasons still hold. New
records are added with the next free number; a superseded record keeps its
text and gains a note pointing at its replacement.

## The shape of the system

| Layer | What lives there | Where it is documented |
| :-- | :-- | :-- |
| Pure contract | declarations, the schema, no QGIS import | [Pure contract layer](https://archont561.github.io/qgis-sdk/python/pure-contract-layer/) |
| Runtime | services, scoped host, jobs | [Scoped plugin runtime](https://archont561.github.io/qgis-sdk/python/scoped-plugin-runtime/) |
| Adapters | the Qt and QGIS bindings behind the services | [Desktop bindings](https://archont561.github.io/qgis-sdk/python/desktop-bindings-and-native-surfaces/) |
| Bridge | typed TypeScript clients over the same contract | [TypeScript SDK](https://archont561.github.io/qgis-sdk/typescript/) |
| Tooling | `qgis-sdk` commands, scaffolding, packaging | [Python guide](https://archont561.github.io/qgis-sdk/python/) |
| Documentation | `apps/docs`, exported static, with llms exports | [Documentation site](https://archont561.github.io/qgis-sdk/contributing/workspace/documentation-site/), [decision-73](../../backlog/decisions) |

## Sources

- `backlog/decisions/` - the records.
- `backlog/docs/plans/` - the roadmap, the service coverage map and the plans the records refer to.
- `AGENTS.md` - the rules that follow from the records and apply to every change.
