---
id: decision-31
title: Bind the plugin context as a class attribute, not a constructor argument
date: '2026-10-25 16:30'
status: accepted
---
## Context

decision-6 injected the typed `PluginContext` "once through construction":
`PluginRuntime.start()` called `plugin_class(context)`, so every plugin class
began with `def __init__(self, ctx: PluginContext): self.ctx = ctx`. The owner
asked on 2026-10-25 for the context to be a class variable instead, set by the
SDK rather than passed to `__init__`, with the author annotating
`ctx: PluginContext` in the class body for typed access.

## Decision

1. **The runtime binds `plugin_class.ctx`.** `start()` sets the attribute to its
   `PluginContext` before constructing the class with no arguments, so
   `self.ctx` is readable everywhere, including `__init__`. `unload()` and a
   failed start remove the attribute again if it is still that runtime's own,
   so the class is plain outside a running lifecycle and never retains a
   closed scope. The attribute name is `qgis_sdk.core.runtime.CONTEXT_ATTRIBUTE`.
2. **The annotation is the typing.** `ctx: PluginContext` in the class body
   declares the attribute for IDEs and type checkers without initialising it;
   the SDK injects no base class, mixin or `Protocol` (decision-6,
   decision-10 still hold: author classes stay plain).
3. **One class, one running runtime.** The most recently started runtime owns
   the attribute; a second start rebinds rather than refuses, so a runtime that
   was never unloaded (a crashed test, a reload) cannot poison the class.
4. **No constructor adaptation.** The runtime still never inspects the
   constructor to decide how to call it. It inspects the signature only after
   `plugin_class()` raised `TypeError`, to turn "missing 1 required positional
   argument: 'ctx'" into a `QgisSdkPluginLifecycleError` that names the change.
5. **Scope.** This applies to `@plugin` classes only. `AlgorithmContext` and
   `JobContext` are built fresh per invocation or attempt and shared class state
   would leak between concurrent runs, so they keep constructor injection
   (decision-11, decision-13). The explicit `instance_factory` still receives
   the context and runs with `ctx` already bound.

## Consequences

- Existing plugins drop two lines and gain `ctx: PluginContext`; the scaffold,
  the smokes and the guides show the new form. A plugin that keeps the `ctx`
  parameter fails at `start()` with an explanatory error, not a bare
  `TypeError`.
- An instance retained after `unload()` no longer has `ctx`; the runtime's
  context object is what tests hold to assert on the closed scope.
- The amendment to decision-6 is limited to the injection mechanism for
  plugins; the rest of that decision stands.
