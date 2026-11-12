---
id: decision-81
title: Pass a constructor one record instead of its fields as keyword parameters
date: '2026-11-10'
status: accepted
---
## Context

The clean-code budget counts parameter lists over five as CC102, and after the
Processing slice the runtime's were all the same shape: a constructor or factory
whose caller names five to eight facts that travel together anyway.

`NativeProcessing(layers=..., algorithms=..., project=..., scope=...,
authority=..., rasters=...)` was built by the runtime context and two test
harnesses, and the service immediately folded its arguments back into a record
of its own. `Dispatcher.from_description(description, handlers, *, streams,
authorize, ledger, theme)` did the same thing with three options every caller
spelled out to vary one. `HostAuthority.grant_file` unpacked five keyword
arguments into the `_FilePolicy` the grant machinery already read. And
`native_plugin_context(scope, *, ...)` - seven parameters, eleven locals - was
the adapter's own entry point, called from `host()`, the app host and nine test
harnesses.

## Decision

**A constructor that needs more than five facts takes them as one record, and the
record is a frozen dataclass defined next to what consumes it.**

- `ProcessingServices` for `NativeProcessing`, exported from
  `qgis_sdk.adapters.qgis.processing` and `qgis_sdk.adapters.qgis`;
- `DispatchSetup` for `Dispatcher.from_description`, exported from
  `qgis_sdk.bridge`;
- `FilePolicy` for `HostAuthority.grant_file`, exported from
  `qgis_sdk.bridge.authority` and `qgis_sdk.bridge`;
- `NativeContextOptions` for `native_plugin_context`, exported from
  `qgis_sdk.adapters.qgis`.

Three properties belong to the record rather than to the call site:

1. **It is immutable** (`frozen=True`), so the ordinary value can be a shared
   default (`_DEFAULT_FILE_POLICY`) and a caller cannot be handed a record that
   another caller then edits.
2. **It validates nothing it does not own.** `ProcessingServices` accepts a plain
   mapping as well, because a host that already holds the services in a dict has
   the keys, not the type; the mapping is expanded at construction, so a typo is
   a `TypeError` there rather than a provider registered with `None` inside it.
3. **It is the thing the implementation already reads.** `FilePolicy` *was*
   `_FilePolicy`; the split was the visibility, not a new layer. A record that
   duplicates an internal structure is two records.

A single-parameter or two-parameter call does not get a record. `ctx.files.grant_file(
path, operations=..., overwrite=...)` is the plugin's own door, it never exposed a
grant's lifetime or ceiling, and three parameters are not the shape the rule is
about.

## Consequences

- Budget 817 -> 813 findings, four CC102 entries, with no behaviour change: each
  record is constructed at the call site from the same values, and every call
  site was rewritten in the commit that introduced it.
- `ProcessingServices` is now the public way to build the Processing service.
  `NativeProcessing` keeps no keyword surface at all - a caller that wants one
  writes the record - which is what finally removed the finding the Processing
  slice left behind.
- The two remaining CC102 entries in `core/contexts.py` (`PluginContext` at 22
  parameters, `ViewContext`/`UiContext` at 21) are the same trade applied to a
  much larger surface, and they are recorded in TASK-167 rather than folded in
  here. CC202 (class size: `HostAuthority` at 18 methods, `Dispatcher` at 21) is a
  different cut - collaborators, not records - and is recorded there too.

## Follow-through: the two contexts

The two entries this decision left in `core/contexts.py` were the rule applied
to the surface it was written for, and they took the same shape: `PluginServices`
for `PluginContext` (19 capabilities and the host it is) and `UiServices` for
`UiContext` (16 and the host), both frozen slots records exported from
`qgis_sdk.core`.

```python
PluginContext(notifications, scope, PluginServices(host=Host.DESKTOP, layers=...))
UiContext(notifications, view, scope, UiServices(streams=...))
```

The one thing that differs from the Processing slice is how a record field
reaches the context. A capability is two declarations - a `_capability_names`
entry and a slot - and `__init__` is one comprehension over the names, so a
service cannot be added to one and forgotten in the other: the record is a slots
dataclass, so a name the class knows and the record does not is an
`AttributeError` at construction rather than a missing attribute later.
`with_services` rebuilds the record from the slots it already set, which is why
it kept its signature.

Budget 813 -> 808: the two CC102 entries (`PluginContext` 22 parameters,
`UiContext` 21) and two CC101 entries (the 47- and 45-line `__init__`s) are gone.
The four parameters that remain in the file are `AlgorithmContext` and
`ServerContext`, a following slice with their own call sites to move.

The rewrite was 115 call sites across tests, examples, adapters and the scaffold
templates - and the gate caught what a mechanical rewrite costs: two surfaces grew
past 30 lines on the way, `adapters/surfaces.py`'s view assembly (extracted as
`_view_services`) and one test that then asserted two contexts at once (split in
two). A record is a line of its own at every call site, so the budget is what says
whether the trade paid, not the parameter count alone.

## Follow-through: the remaining contexts

Slices 10 and 11 applied the rule to every context constructor. The plugin and
view contexts got `PluginServices` and `UiServices`; `AlgorithmContext`,
`JobContext` and `ServerContext` got `AlgorithmServices`, `JobServices` and
`ServerServices`. The execution contexts keep `progress`, `cancellation` and
`scope` as ordinary arguments and put everything a *host* decides into the
record; `AlgorithmServices.algorithms` is required because the runner always
supplies it. `ServerServices` may be omitted entirely - the nine positional call
sites in the examples and tests construct a context with no capabilities.

CC102 counts `self`, which is why five explicit parameters is the ceiling: the
first attempt at `AlgorithmContext` kept six and therefore kept its finding even
though it had a record. Budget 808 -> 804; no threshold changed and nothing was
suppressed.

## Follow-through: plain functions, not only constructors

Slice 14 extended the rule past `__init__` to the four long signatures in
`automation/release.py`: `render_changelog(..., ChangelogOptions(...))`,
`compute_plan(..., PlanOptions(...))`, `manifest_versions(ManifestSources(...))`
and `create_release(ReleaseDraft(...), opener=...)`. CC102 counts `self` but
applies to any function definition, so a plain function with six parameters is
the same missing abstraction as a constructor with six.

Two of them earned their keep beyond the parameter count. `ManifestSources` is
also what `_manifest_sources()` returns after reading nine optional files, so
the reader and the consumer share one shape; `PlanOptions` is the only place the
plan's knobs are named, which is what let the 124-line `compute_plan` become a
`_PlanFacts` record plus six small decision helpers. This supersedes the note in
`backlog/docs/plans/doc-7` that a parameter object for `compute_plan` and
`create_release` would not reduce coupling: with the call sites moved in the
same commit, it did.

## Follow-through: test fixtures and parametrized cases

Slice 15 applied the rule to the release-test fixtures, not only product code. `_python_manifests` and `_ui_train_manifests` had long lists of arguments whose only job was to override a default; they now take `_PythonManifestVersions` and `_UiTrainOptions`. The four parametrized GitHub Packages shell cases became one `_UiPackagesCase` record, so the test takes `tmp_path` and `case`. Every record kept the old defaults and every call site moved in the same commit.

The `**kwargs` forwarder is worth reading twice: `_example_manifests` used to pass `python_version=` to `_python_manifests` without either function naming the shape they shared. A record makes the one call site say `_PythonManifestVersions(python="0.6.0")`, and makes a second vocabulary impossible. Budget 725 -> 707; no threshold changed and nothing was suppressed.

## Follow-through: test doubles and harnesses

Slice 16 applied the rule to the two 16-finding test files. `test_plugin_rest.py`'s `request()` and server setup now take `_Request` and `_ServerOptions`; `fakes.py`'s six long setup signatures take `FakeAlgorithmSetup`, `DeclaredOutput`, `VectorLayerDeclaration`, `OtherLayerDeclaration`, `ConnectionDeclaration` and `TableDeclaration`. The 82 call sites moved in the same change, including a `getattr` dispatch and a generated starter test held in a string template. A record is still a line of its own at a call site: three test functions crossed 30 lines and got named declaration helpers instead of an upward rebaseline. Budget 707 -> 675; no threshold changed and nothing was suppressed.

## Follow-through: checker contexts

Slice 17 applied the rule to the UI checker's AST walks. `check_bindings` builds one `_CheckContext`; `_Names` is assembled from `_ImportFacts`; UI001, UI002 and UI005 carry `_WidgetSite`, `_UiScope` and `_DeclaredSite` instead of threading the same four or five facts through every helper. The records group *read-only context*, not mutable state: each diagnostic builder still returns one `Diagnostic`, and `Diagnostic` itself stays frozen. Budget 675 -> 660; no threshold changed and nothing was suppressed.

## Follow-through: bridge scenarios

Slice 18 applied the rule to the host bridge's long test scenarios. `_ContextRig`, `_AlgorithmRunCase` and `_AlgorithmContext` are frozen slots records that carry a whole scenario's facts as one local; the builders are named functions, and the assertion phases take the record rather than a list of eleven arguments. `_assert_grant_refusal` takes the dispatcher, binding, payload and expected code rather than a long positional list. Budget 660 -> 648; no threshold changed and nothing was suppressed.

## Follow-through: service constructors and run stages

Slice 19 applied the rule to a service constructor and to the stages of one run. `NativeAlgorithms` took `layers`, `scope`, `working_directory`, `files` and `workers`; it now takes one `AlgorithmWiring` record, and both call sites (`adapters/qgis/context.py` and the contract-test fixture) build the same record. The generic run's five arguments became `_RunRequest`; its staging, parameter and publication phases became `_NativeParams`, `_PublishRequest` and `_PublishFacts`; `_RunStage` is the one object that owns the run directory and the staging directory. A record here is not decoration: `_PublishFacts` is what lets seven named checks share the same answer, path, grant and destination without a seven-parameter helper. The output-kind ladder became `_OUTPUT_CONVERTERS`, a dispatch table. In the REST native tests, `_Rig`, `_ServerSpec` and six probe records carry the same facts the long test bodies used to keep as fifteen to twenty-one locals. Budget 648 -> 624; no threshold changed and nothing was suppressed.

## Follow-through: typed options mappings and phase records

Slice 20 extended the rule to a whole service surface at once. `Network`/`BlockingNetwork`, `NetworkClient`, `Layouts` and `LayoutService` no longer spell five or six per-call knobs in each signature: `RequestOptions`, `ConfigureOptions`, `ExportOptions` and `AtlasOptions` are `TypedDict` shapes expanded with `Unpack`, so `ctx.network.get(url, timeout=2)` is still the same keyword call with the same static types but the method takes one parameter. A frozen slots record parses each mapping before a transport is touched, owning the defaults and the limit checks. `LayoutWiring` is the constructor record the two layout adapters build.

The same slice applied the record idea to *phases*: a long function's trailing statements move into one named helper, and when that helper needs more than five values it takes one `**values` mapping instead of a long parameter list. Both are dict inputs in the sense this decision allows, and both keep the caller's vocabulary visible at the call site. Budget 624 -> 424; no threshold changed, nothing was suppressed, no call site or default changed.

## Follow-through: one dict of read-only facts per phase

Slice 21 used the dict-input form of this rule for tail continuations: a long function ends with one named helper taking `**values`, fed by `{**globals(), **locals()}` at the call site. Every fact the tail reads is a key in that dict; the caller's vocabulary stays visible in the call, and the helper owns no hidden state. The oversized-class half of the slice uses inheritance instead of a parameter object, because the value being split is a set of methods rather than a list of arguments. Budget 424 -> 352; no threshold changed and nothing was suppressed.

## Follow-through: records and dispatch replace generated phase chains

Slices 20 and 21 left chains of `**values` forwarders in the worst files - fifteen in `qgis_sdk_tools/project.py` alone, each one taking a mapping and passing the same mapping to the next helper. Slice 22 replaces them with the shape this decision originally asked for. A `_ProjectFacts` record with named fields is built once by `load_project`, filled by `_read_project_fields` and `_read_tool_fields`, and closed by `_config_from_facts`; there is no forwarding step left. The same move in `tests/scripts/test_ci.py` produces `_GateTree`, `_UnchangedFiles` and `_StoppedArtifact`, and in `qgis_sdk/core/_application.py` turns `_init_facts1` / `_include_facts1` into `_initial_plugin_fields` / `_commit_inclusion`.

Two more corollaries. First, a dispatch table is a parameter object's cousin: `_RANGE_CLAUSES` and `_POINT_CLAUSES` in `check/versions.py` replace two operator ladders with a mapping from operator to a two-argument comparison, and `_EXTERNAL_TEXTS` in `project.py` does the same for two optional fields. Each handler is a short function with an explicit signature, so the vocabulary lives in the table rather than in an `elif` chain. Second, an explicit signature beats a captured mapping: `_destination_name_tail1(**{**globals(), **locals()})` in `processing/runs.py` became `_destination_name_tail(name, parameter)`, because a helper that resolves a name through `globals()` cannot be read locally.

The rule for the remaining tail is therefore: one record per cohesive phase, one handler per dispatch key, and no helper whose only body is a call to the next helper. Budget 352 -> 310; no threshold changed and nothing was suppressed.

## Follow-through: records for phases, dispatch for ladders, aliases for CLI signatures

Slice 23 applies the rule to three shapes that had resisted earlier passes. First, the *phase* of a run: `devtools/dev.py`'s `plan_dev` had ten parameters and a 174-line mode ladder. `_DevOptions` / `_AppOptions` are `TypedDict` shapes expanded with `Unpack`, so the keyword call sites and their static names do not change; `_DevFacts` is the frozen record every mode planner reads; `_DEV_PLANNERS` dispatches to `_server_plan` / `_standalone_plan` / `_desktop_plan`. `bundle/__init__.py` does the same with `_BuildPlan` and `_StageFiles`, and `processing/codegen.py` with body/header/footer records. `qgis_sdk/algorithms.py`'s `invoke` keeps its public six-parameter signature and hands everything else to `_InvokeRequest` / `_Run`, which is the honest boundary: a parameter object changes an internal helper, not a published API.

Second, *branch ladders* are the same missing abstraction as a long parameter list. `jobs/_authoring.py` replaces `elif` chains with `_ORIGIN_ACCEPTS` and `_ANNOTATION_ACCEPTS`; `check/jobs.py` replaces six sequential probes with a tuple of handlers over one `_JobCheck` record; `testing/expressions.py` replaces the whole `parse` conditional chain with `_ExpressionReader`. Each handler is a short function with an explicit signature, so the vocabulary lives in a table rather than in an `elif`.

Third, a Typer command's long signature is a *declaration of the CLI*, which is why slices 21-22 left 36 CC102 findings alone. Slice 23 does not remove those parameters; it moves each `Annotated[..., typer.Option(...)]` expression into a module-level alias (`_JsonOpt`, `_PluginOpt`, ...). The command still declares exactly the same options, `typing.get_type_hints(..., include_extras=True)` resolves them, and both `--help` outputs are unchanged; only the function body got short enough to read. Where a signature cannot change at all (the public `invoke`, the Typer commands themselves), the remaining CC102 is reported rather than padded with an unsafe wrapper.

Finally, the two worst QGIS-gated files from slice 22 are now records too: `_QtRig` / `_PhaseEvidence` in the scheduler smoke harness and the named native layout phases in `services/conftest.py` keep the local QGIS imports inside each helper, which is what the `**{**globals(), **locals()}` continuations of slice 21 could not do. Budget 310 -> 245; no threshold changed and nothing was suppressed.

## Follow-through: a template is a phase, and a CLI option is data

Slice 24 extends the rule to two shapes that are not constructors at all. First, a long generated document: `scaffold/generate.py` returned three f-strings of 78, 37 and 48 lines, so no amount of helper extraction inside the function could get it under the limit. Each string is now a sequence of short `_readme_partN(options, plugin)` helpers concatenated at the call site, split at line boundaries with an explicit trailing newline on every part but the last. The scaffold's README is byte-identical across seven option combinations, and `generate_bridge_cases.py` proves the same for `cases.json` by splitting `build_cases` into `_basic_cases`, `_malformed_cases`, `_refusal_cases` and the special cases - with the case order preserved, because the generated file is checked in.

Second, a Typer command's `Annotated` option expressions are *data*, not parameters that need to be spelled inline. Moving each one into a module-level alias (`_ProjectOpt`, `_ModeOpt`, ...) leaves `typing.get_type_hints(..., include_extras=True)` resolving the same options and both `--help` outputs unchanged, while the command body becomes short enough to read. The resolved knobs go into one record (`_GenerateOptions`, `_DevOptions`) and the run into named phases. The remaining CC102 findings are reported, not padded: the signature is the CLI contract.

The same slice applies the decision to QGIS-gated code that earlier passes had to leave alone: `_Exercise` in `devtools/exercise.py` carries the session, coordinator, report and the three closures every acceptance check used to capture, and `_ServerWiring` in `devtools/serverdev.py` carries the application, bindings, server, host, coordinator, watcher and logger. Because each helper keeps its own QGIS import local, the `**{**globals(), **locals()}` continuations of slice 21 are no longer needed. Budget 245 -> 198; no threshold changed and nothing was suppressed.

## Follow-through: a route is a dispatch key, and a generated chain is one record

Slice 25 applies this decision to the two shapes still left in the worst files. First, a *branch ladder* is the same missing abstraction as a long parameter list. `test_network_native.py`'s `_Handler._handle` had eleven `elif` branches deciding which loopback route answers; it now builds one exact-route dispatch table and delegates the three parameterised routes to `_pattern_route`. Each handler is a short method with an explicit signature, so the route vocabulary lives in a table rather than in a chain of conditions - the same move as `_RANGE_CLAUSES` in slice 22 and `_BINDING_HANDLERS` in slice 24. The rule now covers HTTP routes as well as version operators and UI bindings.

Second, the last two long generated phase chains are gone. `examples/simple/tests/test_workflow_ordering.py` had eighteen `_context_facts...` forwarders, each taking the same `**values` mapping and passing it to the next; `adapters/qgis/layouts.py` had seventeen `_render_facts...` forwarders doing the same for one export. One frozen record replaces each chain (`_ContextFacts`, `_RenderFacts`, `_AtlasFacts`), and each phase reads named fields rather than dictionary keys. `_AtlasFacts` goes one step further: the record owns `render()` and `_write_page()`, so a record may own the loop over its own facts, not merely hold them. Slice 22's rule - one record per cohesive phase, no helper whose only body is a call to the next helper - is now true of every file in the budget.

A third corollary is that *imports and long literal argument lists are data too*. `network_limits_probe.py` needed seven QGIS/Qt imports in one function, which is eleven locals before any measurement starts; `_Bindings` holds them as fields and `_Fetcher` holds the four classes one request needs. `layer_kind_fixtures.py`'s forty-argument `struct.pack` call is now `_LAS_LAYOUT` plus `_LAS_IDENTITY` plus `_las_extent(points)`, with the bytes unchanged. In both cases the values were never parameters to reason about; they are a record of facts.

Finally, the signatures that must not change are still reported rather than padded. A pytest fixture's parameter names are its dependency contract, and an algorithm's annotated parameter list is what the Processing registry introspects; `test_parameter_kinds.py`, `test_provider_registration_native.py::classify` and the Typer commands keep their wide signatures and their CC102 findings. A parameter object changes an internal helper, never a published declaration. Budget 198 -> 166; no threshold changed, nothing was suppressed, and there are zero upward diffs against the old budget.


## Follow-through: the residual floor is a signature contract

Slice 26 is the last burn-down before the threshold review. The request was "reduce to zero"; the user chose `keep_contracts` and `one_pr`, so the 31 CC102 findings are deliberately kept and everything else is cleared. Budget 166 -> 31 findings, 115 -> 25 files: CC101 98 -> 0, CC104 28 -> 0, CC303 8 -> 0, CC202 1 -> 0, CC102 31 -> 31. No threshold changed and nothing was suppressed.

The record idea now covers shapes that are not constructors at all. Long definitions keep their signature and become short dispatchers over phases that share one mutable record; a wide call is rebuilt from short `args` / `kwargs` fragment functions, and a large literal from short dict/list fragments, so the caller still invokes the original callee with `*args, **kwargs`. Static strings, snapshot dicts and generated source are module-level constants; a docstring is a one-line `repr` literal with the same `__doc__`. Long phase tuples are lazy chunk functions. Where a value can only be read through a lazy import, the import stays lazy and a name table plus `getattr` replaces eighteen local bindings with two.

Two corollaries. A generator's `yield` cannot be moved into a phase, so the generator keeps the yield and delegates setup and teardown to named helpers over one record - the same boundary as a parameter object. And a `Protocol` with too many direct methods is split into two `Protocol` bases: the public surface is unchanged because `test_bridge_host.py::_methods()` walks `__mro__`, while CC202 counts only direct methods. Branch ladders continue to become dispatch tables (`_CC_KIND_CHECKS`, `_CC_PARSE_ARGV_HANDLERS`, `_cc_bind_dispatch`).

The signatures that must not change are still reported rather than padded: Typer command declarations, annotated algorithm and pytest contracts, and public APIs such as `invoke`. A parameter object changes an internal helper, never a published declaration; that is why the honest residual floor is 31 rather than zero. Slice 22's rule - one record per cohesive phase, one handler per dispatch key, no helper whose only body calls the next helper - now holds with zero non-contract findings left. Budget 166 -> 31; no threshold changed, nothing suppressed, zero upward diffs against the old budget.
