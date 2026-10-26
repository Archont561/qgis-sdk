---
id: decision-42
title: Declare algorithms as plain functions on providers the plugin owns
date: '2026-10-26 14:00'
status: accepted
---
## Context

An author who wants a page-first plugin with a few Processing algorithms meets
three APIs today. `@algorithm` marks a class with a typed `run(inputs) ->
Result` and a request dataclass (decision-11); `Provider` + `@provider.algorithm`
registers such a class so the toolbox can show it (TASK-39); and `invoke(Class,
Request, algorithms=, project=, scope=, ...)` runs one from an action. Making a
provider visible is a fourth step, written by hand in the plugin's lifecycle:
`register_provider(provider, layers=..., algorithms=..., project=..., scope=...)`
in `initGui` and `bridge.unregister()` in `unload`. The scaffold writes none of
it, so the example and doc-12 are the only guides.

Meanwhile `@job` became a plain function with its `JobContext` injected first
and typed keyword inputs (decision-38), and every optional service became a
capability attribute (decision-39). An algorithm is the same shape as a job -
a unit of work with typed inputs, a typed result and an execution context -
differing only in who calls it (the toolbox, the modeler, `processing.run`, or
an action). Keeping it a class with a request dataclass is the one place the
authoring surface still asks for a second form.

## Decision

1. **One form: a function on a provider.** `Provider(id=..., title=...)` is
   the only algorithm container, and `@provider.algorithm` decorates a plain
   function whose first parameter is the `AlgorithmContext` and whose other
   parameters are typed keyword inputs, exactly as `@job`:

   ```python
   tools = Provider(id="field_tools", title="Field tools")

   @tools.algorithm(title="Buffer in a projected CRS", group="Geometry")
   def buffer(ctx: AlgorithmContext, layer: LayerInput, distance: Metres) -> VectorLayerInfo:
       ...
   ```

   `id=` and `title=` derive from the function name when omitted, as for
   `@job` and `@plugin`. Registration is validated at decoration: one leading
   context parameter, every input mapped to a host parameter kind, a unique id
   inside the provider. Nothing is injected at decoration time; a test calls
   the function with a fake context.
2. **Parameter kinds are type aliases.** `LayerInput`, `CrsInput` and `Metres`
   become annotation aliases - `LayerInput = Annotated[str, LayerParameter()]`
   and so on - so `layer: LayerInput` is the usual spelling, while the marker
   classes `LayerParameter`, `CrsParameter`, `MetresParameter` keep the
   explicit `Annotated[...]` form available. Plain `str`/`int`/`float`/`bool`
   inputs become text, integer, double and boolean parameters; anything else
   is refused at registration with the field name and the supported kinds,
   unchanged.
3. **The plugin owns its providers.** A `@plugin` class lists them in a class
   attribute, `providers = [tools]`. `PluginRuntime.start()` registers every
   listed provider with the host's Processing registry when the context
   carries the native services, and `unload()` removes them; a plugin
   outside QGIS (the fakes, standalone Qt) lists the same providers and
   registers nothing. Two plugins registering one provider id are refused by
   name. `describe_plugin` is unchanged: providers are host-side
   registrations, not page-callable operations, so the plugin-description
   contract, `HOST_FINGERPRINT` and the generated clients do not move.
4. **One runner.** `invoke(function, ctx, *, progress=None, cancellation=None,
   add_to_project=True, **inputs)` runs an algorithm from any context that
   carries `algorithms`, `project` and `scope` (a `PluginContext` in an
   action, a `JobContext`, or an `AlgorithmContext` for composition), building
   a fresh `AlgorithmContext` per invocation as decision-11 required. The
   toolbox adapter calls the same function with the same context type.
5. **The class form goes.** `@algorithm` on a class, `run(inputs)` with a
   request dataclass, `invoke(Class, Request, ...)` and the public
   `register_provider` glue are removed in the same minor, the way the `@job`
   class form was. `register_provider` stays as the adapter's internal
   implementation of point 3. `qgis_sdk.reference` is rewritten as functions
   on `reference_provider`.

## Consequences

- An experimental 0.x breaking change: it joins the next unreleased minor's
  migration notes in doc-12 (`run(self, inputs)` → function; `Annotated[str,
  LayerInput()]` → `LayerInput` or `Annotated[str, LayerParameter()]`;
  `invoke(Class, Request, ...)` → `invoke(function, ctx, **inputs)`; delete the
  `register_provider` lines, add `providers = [...]`).
- decision-11 is superseded for the authoring form; what it settled about
  execution - a fresh context per invocation, outputs copied into the user's
  destination, `FlagNoThreading` until worker-thread execution is qualified,
  cancellation observed at phase boundaries - carries over unchanged and its
  open questions (mid-flight cancellation, thread affinity) stay open under
  this decision.
- The scaffold can now write a complete algorithm in one file next to the
  actions, and `metadata.txt`'s `hasProcessingProvider` is derivable from
  `providers` (decision-43).
- `AlgorithmContext` gains nothing; the function receives what the class
  held as `self.ctx`.
