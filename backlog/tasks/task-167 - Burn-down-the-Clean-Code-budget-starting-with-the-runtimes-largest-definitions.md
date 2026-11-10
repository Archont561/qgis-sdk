---
id: TASK-167
title: Burn down the Clean Code budget, starting with the runtime's largest definitions
status: In Progress
assignee: []
created_date: '2026-11-10 11:50'
labels: []
dependencies: []
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-166 makes the Clean Code metrics a gate by freezing today's 939 findings as `clean_code_budget.json`. This task is the other half: the budget only ratchets if somebody turns the ratchet, and the largest entries are the ones worth turning first, because they are the definitions a change to the runtime has to read before it can be changed safely. Each slice extracts cohesive helpers behind unchanged behaviour and lowers the budget in the same commit; the budget diff is the evidence, since nothing else in the repository records that a function got shorter.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The five largest definitions are split behind unchanged public behaviour: `bridge/dispatch.py` (756-line class), `http/_server.py` (699-line class, 379-line function), `bridge/host/_handlers.py` (602-line function), `generate/_generator.py` (588-line class) and `bridge/authority.py` (520-line class).
- [ ] #2 Each slice lowers `clean_code_budget.json` in the same commit, and the existing suites pass without a test rewritten to fit the new shape.
- [ ] #3 The outstanding findings are recorded by rule and by file in this task, so the next slice does not have to re-measure the tree.
- [ ] #4 After the five slices, the thresholds are reviewed: any metric the tree now meets everywhere is tightened in `[tool.rude]` and the budget re-baselined, so the ratchet moves rather than the number merely shrinking.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Slice 1 (landed): the branch rules, not the size rules.** 939 -> 893 findings, no file left with more of anything than it had. CC103 35 -> 19, CC302 26 -> 8, CC303 77 -> 70, CC101 486 -> 481; two files left the budget entirely (`qgis_sdk_tools/rest.py`, `qgis_sdk_tools/ui_yaml.py`).

What the slice changed: guard clauses and lookups instead of return chains (`_item_kind`, `_transport_failure`, `_send`, `_name`, `_scalar`, `_coerce`, `_schema`, `emit`, `pull`, `_step`); named predicates instead of long boolean chains (`_is_number`, `_is_bare_origin`, `_is_local_path`, `_is_module_member`, the `_server` parameter validators); and one table where a chain of `if` was a mapping (`_ACCESSORS`, `_FAILURE_CLASSES`, `_TYPE_NAMES`, `_CONVERTERS`, `_ITEM_KINDS`). Two extras were needed to keep the ratchet honest rather than to shrink anything: `Job._ready` moved to a module function so the step machine's helpers did not push the class past 200 lines, and `Subscription`'s frame handling folded into `_queue_frame` so it stayed at 15 methods.

**What is left.** The size rules are the budget now: CC101 481, CC104 128, CC102 121, CC303 70, CC202 29 / CC201 33, plus 19 CC103 in functions that are themselves too long (`dispatch.dispatch` 19 returns, `processing._value` 16, `_parameter` 15, `form.input_for` 13, `_emit._inline_validator` 15, `webengine._decide` 11, `expressions._compare` 10), 8 CC302 in `tests/smoke_support`, and 4 CC301 (`release._cmd_verify_versions`, `_server._rest_stream`, `_server._close`, `check/jobs._imports_in_body`).

The next slice pays twice if it starts where the returns are: `dispatch.dispatch` is inside the 756-line class, so splitting the endpoint's decisions is the same work as splitting the class. That is why AC 1's five largest definitions are the entry point.

<!-- SECTION:NOTES:BEGIN -->
Baseline from TASK-166: 939 findings in 268 files - CC101 486, CC104 128, CC102 121, CC303 77, CC103 35, CC201 33, CC202 29, CC302 26, CC301 4. CC301 (nesting) is the closest to clean with 4 findings and is worth taking first: it is the rule whose fix is most often "return early", and the smallest diff of the set.
**Slice 2 (landed): the generator, split by when the work may happen.** 893 -> 882 findings, 266 -> 265 files; `generate/_generator.py` leaves the budget entirely (CC101 6, CC104 1, CC201 1, CC202 1, CC303 2 -> 0), so the 588-line class with ~35 methods is gone rather than smaller.

The cut is the order, not the line count. `_Naming` (`_naming.py`) decides every exported type name first, because a parent's field type is the child's name and rendering while descending would point the parent at a name not yet chosen. `_Collector` (`_collect.py`) reads the description into `_Action`/`_Stream` and asks naming for those names on the way down. `_Rendering` (`_context.py`) is the frozen dataclass of what rendering needs - surface, operations, names - so no renderer takes four arguments. `_Frames` (`_frames.py`) renders what surrounds the operations (error class, stream support types, the `Operations`/`Streams` map, the event unions) and `_Members` (`_members.py`) renders the members themselves. `_Generator` stays the façade `_api.py` already constructed, so no caller changed. `_emit.py` now asks a `_Namer` Protocol for `name_for` instead of importing `_Generator` under `TYPE_CHECKING`, which takes the dependency direction out of the emission helpers.

Renderings are byte-identical before and after for all five entry points (host module, host schema, the host description as a plugin, a plugin module and its schema): the refactor was verified by output, not by the suite alone. Runtime suite unchanged at 2957 passed, 129 skipped with the two environmental `test_app_build` failures; `tests/scripts` 332 passed.

The honest cost: moving the long methods into new files unchanged would have booked 8 findings against paths the budget had never seen, which the gate refuses. The same slice therefore split them too - `_action`/`_stream` with `_action_schemas`/`_stream_schemas`, `_operations_map`/`_streams_map`, `register` into `_name_object`/`_twin_of`/`_name_branch`, and `render`/`render_schema` into one method per piece of a rendering. Without that, the total would have fallen by one and the budget would have grown three files.

**The generator's whole-description properties (same slice).** The generator had 87 example-based tests and no property test at all, so a slice that changes how it renders had only examples to lean on. `tests/test_bridge_generate_properties.py` now pins what has to hold for descriptions nobody wrote down: declaration order never reaches either module, each module lists every declared id once, both modules carry the same fingerprint and plugin id, and an action declaring events, a stream declaring a result, a stream with no event kind, an event kind the frame does not carry, a duplicate id or one title declared in two shapes are each refused. Ten tests, and the one refusal the suite had never reached - two shapes under one title - now executes: `generate/_naming.py` is at 100%, the package at 98%.

**Slice 3 (landed): the dispatcher, split into the four things a call can be.** 882 -> 866 findings; `bridge/dispatch.py` goes from 17 findings to 2, and the 756-line, 35-method `Dispatcher` is now a 197-line, 21-method façade over a new `bridge/endpoint/` package (5 modules, 1045 lines, all clean on their first commit).

The cut is the order the endpoint decides in, one role per module: `_registry` holds what may be called, `_views` who may call it (bindings, generations, the handshake and its contract), `_streams` what is already running (a `_Book` of subscriptions and the calls that drive it), `_calls` the invocation itself plus the release call beside it. `_wire` owns what crosses the wire and the checks a value passes first; `_refusals` owns the one way a call stops.

That last module is the idea the six long methods needed. Each of them was a chain of `if <bad>: return failure(...)` - `dispatch` alone had 19 returns and 15 branches - so the happy path was unreadable. A refusal is not an error, it is the reply the caller gets, so a check now raises `QgisSdkRefusal` carrying that reply and `Dispatcher.dispatch` is the single place that catches it: `_invoke_reply` and `_subscribe_reply` read as the list of steps they are, with one return and no branches. The exception carries the `QgisSdk` prefix for the reason `test_error_names.py` gives - nothing in the runtime may define an unprefixed exception class, because one day one of them reaches user code.

Two findings are left in `dispatch.py` and both are deliberate, not leftover:

* **CC202, 21 methods.** The endpoint's contract *is* 21 calls - register four kinds of operation, read two collections, mint a binding, handshake, dispatch, pump, emit, dispose, advance, track, watch, unwatch. Every one of them is a one-line forward to a role, and each has call sites outside this module (91 for `pump`/`emit`/`subscriptions`/`dispose` alone). Narrowing it is an API decision - the roles are already behind it as `dispatcher.registry` and friends would need to be - and hiding it behind a `# noqa` would make the budget record a shape the class does not have.
* **CC102, 7 parameters on `from_description`.** `description`, `handlers`, `streams`, and the three knobs the host supplies (`authorize`, `ledger`, `theme`). Grouping them into a parameter object changes a public factory signature for a metric; the rule's own advice is right, and it belongs to the same API decision as CC202.

**Tests.** The refactor is verified by the existing suite (which is the whole point of AC 2) and by two new modules: `test_bridge_dispatch_properties.py` pins the six promises that hold for *any* message - every call is answered with its own call id, every reply is JSON-safe, an invocation runs its handler exactly once and only when it succeeds, a stale binding is refused for every kind, a view without a grant runs nothing, an operation outside the allowlist is refused by name - and `test_bridge_endpoint.py` pins the edges the roles own (a description the wiring cannot read, a non-callable handler or factory, a factory that raises, a source that raises in `start`, a stream that is neither iterator nor push, malformed calls of each streaming kind, a binding with an empty view or origin, a release payload that is not an object). `bridge/dispatch.py` and the whole `bridge/endpoint/` package are at 100% line coverage; the runtime suite is 2999 passed / 129 skipped with the two environmental `test_app_build` failures.

**Slice 4 (landed): the handler table, split by the namespaces the ids already declare.** 866 -> 860 findings, 265 -> 263 files; `bridge/host/_handlers.py` and `bridge/host/_services.py` both leave the budget entirely (CC101 4, CC104 1, CC303 1 -> 0), so the 602-line function holding 84 nested closures is gone rather than shorter.

The cut is the namespace. An operation id is already `namespace.name` - `canvas.*`, `project.*`, `algorithms.*` - so the handlers were split along the lines the contract declares: eight modules under `bridge/host/handlers/`, one per namespace (or per small group of them: `_layers` also answers `rasters.*` and `files.export`, `_algorithms` also answers `layouts.*`), each registering a `HANDLERS` dict that answers its own ids and nothing else. `handlers/__init__.py` merges them into the one table the registration reads, and `_handlers.py` is now registration only. Before anything moved, the closure block was parsed and matched against the id table: 84 closures, 84 entries, no orphans - which is why the move could be mechanical.

**What a handler receives.** `_context.py` holds `_Host`: the services, the view's authority (one property, since the authority is the services' own), and the open edit sessions the lifecycle operations share. The optional services became properties, so a host that left one out still fails by capability name - `this host has no canvas service configured` - and never answers with nothing (decision-54 point 3). `plugin_file` moved onto it as well: a path still crosses as the plugin's own ref, and a host without a files service still refuses rather than quietly passing a string (decision-20).

**The rest of the file, by what it is.** `_sources.py` holds the four push sources behind the streaming ids and the `EditingSessions` registry; `_support.py` the helpers the handlers share (`_plain`, `_wire`, `_offsets` and the page maths, `_algorithm_wire`, `_resolve_input`, `_result_for_view`, `_fetch_request`, `_response_event`, `_feature_query`). The dependency direction runs one way - `_support` <- `_sources` <- `_context` <- `handlers/*` <- `_handlers` - so no module imports the registration that reads it.

**The three smaller long definitions in the same area.** `_algorithm_wire` (43 lines) is now the description it spells plus `_parameter_wire`, which is the parameter branch it was mostly made of. `register_host_operations` (47 lines) is the four steps it was: `_operations` builds the protocol operations, `_refuse_taken` the conflict check that has to run before anything is registered, `_register` the loop that picks `register_bound` or `register_bound_stream` by whether the id declares events, and the handler reaches its host through `partial`, so no closure captures the loop variable. `HostServices.from_context` (42 lines, 12 branches) kept its field list and gave its two defaults to `_authority_of` and `_network_of`, and the "may be absent" fields to `_optional_service`.

**Tests.** The behaviour is the existing suite's: 2999 passed, 129 skipped with the two environmental `test_app_build` failures, `tests/scripts` 332 passed, and no test needed rewriting for the new shape. `bridge/host/_handlers.py` is at 100% and `bridge/` at 95%. One new module, `test_bridge_host_handlers.py`, pins the shape the merge now depends on: every declared id is answered exactly once, no module shadows another's key, and a namespace belongs to one module - the three ways a table like this can go quietly wrong.

**What is left of AC 1.** `http/_server.py` (699-line class, 379-line function) and `bridge/authority.py` (520-line class). Every other finding in the tree is a size or return-count entry recorded in this task's earlier notes.
<!-- SECTION:NOTES:END -->
