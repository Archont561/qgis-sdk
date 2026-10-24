---
id: decision-26
title: Derive the bridge allowlist and the generated client from one declared manifest
date: '2026-10-24 21:10'
status: accepted
---
## Context

[TASK-17](../tasks/task-17%20-%20Generate-checked-in-TypeScript-contracts-clients-and-validators.md)
has to generate typed clients, operation maps and validators, while
[decision-18](decision-18%20-%20Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md)
forbids duplicating the contract by hand. Two inventories already exist and can
disagree:

- `describe_plugin(cls)` produces a `PluginDescription` whose actions carry
  `id`, `title`, `handler`, `request` and `result` - a complete, schema-carrying
  manifest, derived from `@action` methods without constructing the plugin.
- `Dispatcher.register(BridgeOperation(id, title), handler)` builds the
  allowlist by hand. `BridgeOperation` carries no schemas at all, and
  `Dispatcher(description=...)` only *advertises* the description.

One handshake reply therefore ships `plugin.actions[].id` from the description
and `operations[].id` from the allowlist, and nothing forces them to agree. A
client generated from either can name an operation the other does not have, and
the failure surfaces at runtime as `unknown_operation` rather than at build
time.

The dispatcher also handed the payload straight to the handler, so a misspelled
or extra argument was accepted silently unless the handler itself refused it.
That contradicts what [decision-22](decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md)
promises: strict inputs, extensible results.

## Decision

**One manifest drives the allowlist, the handshake and the generated client.**

- `BridgeOperation` carries the declared `request` and `result` schemas, and
  `to_dict()` advertises them in the handshake so a client can validate what it
  is about to receive.
- `Dispatcher.from_description(description, handlers)` and
  `Dispatcher.from_runtime(runtime)` project the allowlist from a
  `PluginDescription` (or its JSON form) and `PluginRuntime.actions`. The
  handshake's `operations` is then the same set the description names, sorted by
  id, so the two inventories cannot diverge. Hand registration stays for streams
  and tests, but it is no longer the way a plugin's surface is wired.
- **Inputs are strict.** A declared request schema is validated before the
  handler runs: unknown properties are refused (`additionalProperties: false`
  is what the declaration generator emits), missing required properties are
  refused, integers are held to the safe-integer range, and `true` is not `1`.
  A refusal is `invalid_payload` carrying the field path.
- **Results are lenient.** A declared result schema is validated after the
  handler returns: required properties must be present and correctly typed,
  unknown additive properties are tolerated. A refusal is `invalid_result`
  carrying the field path, never the value.
- Payloads are bound to the handler as **keyword arguments**, because the
  declaration already describes them as a named-argument object. A parameter the
  method does not declare cannot reach Python at all.
- The schema subset is the one `qgis_sdk.declarations` already emits
  (`object`/`string`/`integer`/`number`/`boolean`/`null`/`array`/`anyOf`/`enum`,
  plus `required`, `minimum`/`maximum` and `additionalProperties`). Validation is
  implemented in the SDK rather than delegated to `jsonschema`: `typer` is the
  only runtime dependency, and a QGIS plugin should not gain a validator
  dependency to speak its own contract. A construct outside the subset is
  refused loudly, the way an unsupported annotation is.

Regeneration, drift checks and the `contract_fingerprint` belong to
[TASK-17](../tasks/task-17%20-%20Generate-checked-in-TypeScript-contracts-clients-and-validators.md);
this decision only makes the manifest the single object they can read.

## Consequences

- A hand-wired dispatcher that declares no schemas keeps working unchanged:
  validation only applies to operations that declare one.
- Strict inputs are a behaviour change for any caller that was relying on extra
  keys being ignored. Nothing in this repository consumed the dispatcher before
  it shipped, and the bridge has not been released, so the change costs nothing;
  a future lenient mode would have to be justified by a real consumer.
- The generated client and the host validate against the *same* schemas, so
  TASK-17 cannot drift from the host without the declaration changing first.
- Because results are lenient and inputs are strict, an additive host change is
  safe for an older frontend while a renamed or removed input breaks at compile
  time in the generated client.
