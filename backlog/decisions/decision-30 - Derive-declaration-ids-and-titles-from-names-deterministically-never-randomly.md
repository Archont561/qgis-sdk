---
id: decision-30
title: Derive declaration ids and titles from names deterministically, never randomly
date: '2026-10-25 15:40'
status: accepted
---
## Context

Through 0.3.0 every declaration decorator required `id=` and `title=`, so a
plugin with eight actions repeated its method names eight times. The owner asked
on 2026-10-25 for ids to be derived by default, with an explicit value still
winning, and suggested a class name plus a random slug.

An id is not a label here. The bridge dispatches a request by action or stream
id, the generated TypeScript client bakes the ids in as properties, the
Processing adapter uses the algorithm id as the QGIS algorithm name, and
`CONTRACT_FINGERPRINT` is hashed over the description. A slug that changed on
each import would make a client generated at build time miss every id the host
exposes at runtime and would make `generate_bridge_clients.py --check` fail on
every run.

## Decision

1. **Derived, not random.** A missing id or title is a pure function of the
   decorated name. A class id is the snake_case class name plus six hex digits
   of `sha256("<module>.<qualname>")`: unique across plugins, algorithms and
   jobs that share a class name, and identical on every import until the class
   is renamed or moved. A title is the name spaced into words.
2. **Methods carry no suffix.** An action or stream id is the plain method
   name. It is already unique inside its class, and a suffix would turn
   `client.list_layers(...)` into a quoted property for no gain.
3. **Explicit always wins and is validated early.** A given `id=` or `title=`
   is checked when the decorator is called, before the class exists, exactly
   as before. `Provider(...)` has no class to derive from and keeps requiring
   both.
4. **Bare form everywhere a name exists.** `@plugin`, `@action`, `@algorithm`,
   `@job` and `@provider.algorithm` accept the bare spelling; `@stream` keeps
   its call form because `events=` is mandatory.

## Consequences

- An author who renames a class changes its derived id, and therefore the
  description and fingerprint; the guide says to pin `id=` before publishing a
  contract that must survive refactors. Nothing changes for explicit ids.
- The id grammar and the bridge's `DECLARATION_ID_PATTERN` are untouched: a
  derived id is `[a-z][a-z0-9_]*`, a subset of what was already accepted, so the
  wire contract and `PLUGIN_DESCRIPTION_SCHEMA_VERSION` do not move.
- `derive_id` and `derive_title` are public in `qgis_sdk.declarations` so a
  scaffold or a documentation tool reproduces the same spelling.
