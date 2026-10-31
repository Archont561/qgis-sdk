---
id: decision-71
title: Span the grant vocabulary across the page, the console and the plugin HTTP allowlist, and defer the destructive annotation
date: '2026-10-31'
status: accepted
---
## Context

decision-54 point 2 fixed one grant vocabulary for three clients: the page's
`[tool.qgis-sdk.web] grants`, an `[tool.qgis-sdk.agent] grants` and a new
`[tool.qgis-sdk.console] grants`, with destructive operations carrying an
annotation "the agent consent list and the audit log use".

The middle client no longer exists. decision-49 - the runtime agent surface,
its loopback transport, its consent list and its MCP adapter - was withdrawn on
2026-10-29 and replaced by TASK-74: MCP stays in the developer CLI, and the
runtime's outward client is an explicitly hosted, authenticated, allowlisted
**plugin HTTP API**. 0.8.0 shipped accordingly, and its migration notes state
that there is no `qgis_sdk.agent`, no `[tool.qgis-sdk.agent]` metadata, no
`AGENT` check rule and no consent surface. There is also no audit log anywhere
in the tree; the only "destructive" notion is `qgis_sdk_tools.mcp`'s
`destructiveHint`, which describes CLI commands.

So TASK-84's premise named one client that was deliberately removed and one
artefact (an audit log) that was never built. Building either would reintroduce
a withdrawn design or invent a new surface inside a task scoped as "small".

## Decision

1. **The vocabulary spans what exists.** `<service>.<operation>` ids and the
   grant names of `qgis_sdk.bridge.host.host_grant_names()` are read by the
   page (`[tool.qgis-sdk.web] grants`), the console
   (`[tool.qgis-sdk.console] grants`, unset meaning every operation because the
   console is the plugin's own developer) and the coverage map. Both sections
   are validated by one reader, so an unknown name is the same `GRANT001` in
   whichever section it appears, with one remediation listing the vocabulary.
   `qgis-sdk check --grants` prints the client × operation matrix.
2. **The HTTP allowlist is a client, not a third operation table.** It is shown
   in the matrix's client list and names **plugin action and stream ids**, not
   host operations. It reuses no host-grant names because it has none to reuse;
   an unknown action is still refused by name when the server is constructed.
3. **The destructive annotation and the consent/audit consumers are deferred.**
   They are recorded on TASK-84 as deferred to TASK-105 (the authority and
   threat model, doc-26), which is where every grant and check has to cite a
   row of one document. Adding an annotation now would publish a manifest field
   no consumer reads.
4. **The coverage map is enforced, not maintained by habit.**
   `tests/scripts/test_service_coverage.py` fails when
   `qgis_sdk.bridge.host.HOST_OPERATIONS` declares an operation doc-22 does not
   list, when a row names an operation that no longer exists, when an operation
   is listed twice, or when a grant name is missing from the table.

## Consequences

- decision-54 point 2's "agent" clause is superseded by decisions 49 and 71;
  its "one vocabulary" intent stands.
- Every later service sprint (TASK-85 to 89, 91 to 94) adds its rows to doc-22's
  host-operations table in the same change, or the gate fails.
- TASK-84's AC 3 keeps its documentation half and loses the consent/audit half;
  that half moves to TASK-105, which needs it before it can write the authority
  matrix.
- Console grants are declared and printed but not enforced at runtime yet: the
  console builds a `PluginContext` directly rather than a bridge view registered
  with `only=`, so narrowing it needs its own seam. Recorded on TASK-84.
