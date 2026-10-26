---
id: decision-14
title: Enforce QGIS free import boundaries during check
date: '2026-10-16 08:05'
status: accepted
---
## Context

Pure declaration inspection and logic tests must run without QGIS. Deferring an import changes when it executes, not whether a runtime can resolve it.

## Decision

Proposed check errors: QGIS001 rejects module-import-time qgis imports outside explicitly native modules; ARCH001 rejects pure-to-native adapter dependencies. AST checks include imports in module/class scope, try/except and module conditional blocks, with recognized TYPE_CHECKING guards allowed. Models/service contracts remain runtime-QGIS-free even inside functions. Native view factories may defer imports; explicit native adapters may import at module scope but must not be eagerly re-exported by pure package entry points.

Do not resolve type-checking-only native annotations into live classes during pure schema inspection. Public bridge/algorithm schemas use supported SDK values/handles, not native annotation objects. Add subprocess import-boundary tests that block native imports; static checks alone cannot prove safety against dynamic imports, top-level calls or third-party dependency chains. Resolve dynamic-import policy explicitly and avoid claiming complete side-effect analysis.

Runtime composition selects QGIS adapters; pure tests select fakes. Native UI uses the bindings supplied through qgis.PyQt. CLI runtime discovery/configuration must establish PyQGIS importability; initializing QgsApplication is a separate step where required. No arbitrary pip install qgis, hard-coded sys.path guesses or silent fake fallback. Reuse source checks in build.

## Consequences

- Diagnostics identify path/line, rule and actionable remediation; native exemption scope must be narrow/configured.
- Importing a declaration in a subprocess is not a security sandbox.
- Rules and runtime-detection APIs are proposed, not implemented checks.

## Status review (2026-10-24): stays `proposed`

What exists is the *test-level* boundary, contributed by TASK-11: an AST walk over
the pure layers and a subprocess import that blocks `qgis`, PyQt and pydantic while
exercising declarations. What the decision names, and what does not exist, is the
reported check: the `QGIS001` and `ARCH001` diagnostics have no implementation
anywhere in the tree, there is no `check` command to emit them, and
[TASK-16](../tasks/task-16%20-%20Implement-non-mutating-check-and-QGIS-import-diagnostics.md)
(which owns the check command and the diagnostics) is still `To Do` in milestone
m-3. The Consequences section's "Rules and runtime-detection APIs are proposed, not
implemented checks" therefore remains literally true.

**Promotion condition:** promote when TASK-16 emits path/line/rule/remediation
diagnostics for the same boundaries the tests already guard, in the build as well
as the check command. Until then the guard is real but the decision's contract is
not delivered.

## Progress (2026-10-25): check emits the diagnostics; build does not yet

TASK-16's first slice (`qgis_sdk.check`, `qgis-sdk check`) now emits `QGIS001`
and `ARCH001` with path/line/column, rule and remediation, treats module, class,
`try`, `with` and module-level `if` as import time, allows function bodies and
`if TYPE_CHECKING:`, and narrows the native exemption to configured globs
(`[tool.qgis-sdk.check] native-modules`, `--native`). The status stays
`proposed` for the half of the promotion condition that remains: `qgis-sdk build`
(TASK-21) calling `check_project` in-process.

## Status review (2026-10-26): promoted to `accepted`

Implemented by TASK-16 and enforced in every gate since 0.4.0, so the status
moves to `accepted`:

- `qgis_sdk_tools.check.imports` emits QGIS001 and ARCH001 from an AST walk
  that covers module, class, `try`/`except` and conditional scope and
  honours `TYPE_CHECKING` guards; `test_check_imports.py` is its test.
- The SDK applies the rule to itself: `test_pure_imports.py` scans the tools
  tree for literal `PyQt6`/`qgis` imports (adapters load through
  `importlib.import_module` tables), and a subprocess test proves the pure
  packages import without QGIS present.
- Runtime composition picks the QGIS adapters; pure tests pick fakes
  (decision-6/7); runtime discovery in the CLI establishes PyQGIS
  importability and never installs QGIS.

decision-43's rule that the author's project carries no `webview.py`,
`metadata.txt` or `classFactory` is the same boundary seen from the author's
side: QGIS-specific entry points are generated, never written by hand.
