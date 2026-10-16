---
id: decision-14
title: Enforce QGIS free import boundaries during check
date: '2026-10-16 08:05'
status: proposed
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
