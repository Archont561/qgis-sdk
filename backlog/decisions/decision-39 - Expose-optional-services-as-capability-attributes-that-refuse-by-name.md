---
id: decision-39
title: Expose optional services as capability attributes that refuse by name
date: '2026-10-25 23:30'
status: accepted
---
## Context

Every context (`PluginContext`, `UiContext`, `AlgorithmContext`,
`JobContext`) carries services a host *may* provide - `workers`, `network`,
`layers`, `project`, `settings`, `styles`, `algorithms`, `desktop` - as
`Optional` dataclass fields, each paired with a `require_<name>()` accessor
that raised `QgisSdkUnsupportedCapabilityError(<name>)` when the slot was
`None` ([decision-32](decision-32%20-%20Offer-the-curated-services-on-PluginContext-and-build-the-web-view-surface-from-it.md)).
The rule behind the pair is sound: a pure or standalone host must fail on the
first touch, by capability name, never with `AttributeError: 'NoneType' ...`
deep in author code. The spelling was not: author code read
`self.ctx.require_layers().open_vector(...)` and
`await ctx.require_workers().offload(...)` everywhere, the `Optional` field
sat beside the accessor inviting `ctx.layers.open_vector(...)` that type
checkers flagged and hosts without the service broke, and the user asked for
the accessors to be hidden.

## Decision

Each optional service is a **capability attribute**: a descriptor typed as
the service (not `| None`) whose read checks the scope is open and either
returns the very instance the host passed or raises
`QgisSdkUnsupportedCapabilityError(name)`. Author code spells
`ctx.layers.open_vector(...)` and `await ctx.workers.offload(...)`; the
failure mode and its name are unchanged, only where the check lives moved.

- `require_<name>()` is removed, not deprecated - pre-1.0, one spelling.
- Probing is explicit and separate from use: `ctx.has("workers")` answers
  without touching the scope and `ctx.capabilities` lists what was provided.
  `has()` raises `ValueError` for a name the context never carries, so a
  typo cannot read as "not provided".
- Constructors keep their keyword arguments
  (`JobContext(..., workers=pool)`), so hosts, fakes and tests assemble
  contexts exactly as before. The contexts stop being dataclasses: they are
  slotted, immutable classes (`AttributeError` on assignment) with a `repr`
  that names the capabilities provided.
- Null-object services ("always present, every method raises") were
  rejected: they move the failure from first touch to first call, make
  `is None` silently meaningless and double every Protocol with a stub.

## Consequences

- `qgis-sdk-runtime` 0.6.0 carries this as a second breaking change beside
  decision-38; doc-12's 0.6.0 migration note lists the renames
  (`require_native()` → `desktop`, `require_<x>()` → `<x>`, slot probes →
  `has()`).
- `HostServices.from_context` and the native tests that probed slots use
  `has()`; `examples/simple`, the scaffold template, the devtools exercise
  and every guide read the attribute.
- `tests/test_contexts.py` pins the attribute refusal for every capability on
  every context, the probes, the closed-scope refusal, immutability and the
  absence of `require_*`.
- Amends decision-32's "every optional capability has a `require_<name>()`";
  the rest of decision-32 (same instances on both sides of the bridge) stands.
