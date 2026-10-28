---
id: decision-66
title: Unify declaration introspection with describe and declaration methods
date: '2026-10-28 15:42'
status: accepted
---
## Context

The owner wants one `describe` API for authored declarations and a convenient
`.describe()` method, including actions stacked with Desktop bindings. The
existing dispatcher covered plugins, jobs and algorithms, while actions,
surfaces, bindings and providers had separate inspection routes. Decisions 6,
10 and 49 favoured leaving author classes/functions untouched apart from
metadata; this decision amends that detail while preserving unwrapped calls.

## Decision

- Export `qgis_sdk.describe(target)` and retain the existing narrow helpers for
  compatibility. Decorated plugin classes, actions, streams, job and algorithm
  functions, UI-bound surfaces and UI handlers expose `.describe()` through the
  same dispatcher. `Provider.describe()` remains, and `describe(provider)`
  supports it. SDK `Dialog`/`Dock` subclasses inherit the convenience method.
- Resolve stacked toolbar/menu/shortcut metadata with the declaration: actions
  and surfaces expose `bindings`, and plugin descriptions expose registered
  surfaces and bindings. UI handler `@on`/`@subscribe` metadata appears in
  `wires`, including when combined with an action or stream.
- Keep the bridge's existing `to_dict()`/`to_json()` representation unchanged;
  bindings and wires are local introspection data, not wire fields. Keep the
  QGIS-free lower-layer boundary: higher layers register their describers.
- No handler is wrapped or executed to describe it. Resolving annotations is
  only safe for trusted author code. The name `describe` is reserved: refuse a
  conflicting existing attribute with migration guidance, never overwrite it.
  This can require a Python-minor migration. The dynamic convenience attribute
  does not guarantee static IDE inference.

## Consequences

- Amends decisions 6 and 10 and TASK-49's no-method rule, while keeping the
  existing callable/class identity and schema contracts. Old narrow helpers stay
  as compatibility APIs rather than being removed.
- Tests must cover both forms, action and surface bindings, UI wiring, name
  collisions, inheritance, no target execution, and unchanged serialized bridge
  contracts. Record actual validation before claiming completion or release.

## Local implementation status (2026-10-28)

At the 2026-10-28 review, the active session branch contained uncommitted
implementation and local validation; at that point it was not merged, released
or CI-qualified; see [TASK-120](../tasks/task-120%20-%20Land-and-qualify-the-unified-declaration-describe-API.md) for remaining landing and migration work.
