---
id: decision-62
title: Write one authority and threat model document and make every check and grant refer to it
date: '2026-10-26'
status: accepted
---
## Context

Authority is enforced in several places - per-view grants (decision-23/27),
agent grants plus consent and token file (decision-49), console (decision-48),
`UiContext.actions` (decision-55), `dev.ui.act` (decision-51), the server
host's request scope (decision-52), the unified vocabulary (decision-54) -
and nowhere described as one model. A reviewer cannot answer "who can make
the plugin do what" without reading eight decisions.

## Decision

1. **doc-26 "Authority and threat model"** (specification) names the
   principals (plugin author, end user at the Desktop, a page in a view,
   an agent in developer or user mode, the console, a server client, the
   operator), the assets (project data, files, credentials via `auth`
   ids, network, settings, the host itself), the trust boundaries (view
   scope, loopback endpoint, server request, vendored runtime), and one
   table of operation class × principal → allowed / granted / consented /
   refused. Every grant name, check rule and refusal message cites a row.
2. **Rules the document fixes.** Deny by default everywhere; grants are
   static in `pyproject` and baked by `build`; consent is per user per
   operation class for agents; destructive and credential-touching
   operations are annotated and audited; no principal reaches `iface`,
   `eval` or arbitrary Qt; developer-mode tools (`dev.*`, `dev.ui.act`)
   never exist in a built plugin; the token file is per session, per
   user, mode 0600, and the endpoint binds loopback only.
3. **`SECURITY.md`** at the repository root points at doc-26 and states
   the reporting path; `qgis-sdk check --security` prints the plugin's
   effective matrix (which principal can do what) and `SEC001` flags a
   grant that exceeds what the plugin's own code uses.
4. **Changes to authority require the document first**: a decision that
   adds a principal, an operation class or a boundary edits doc-26 in the
   same change.

## Consequences

- Reviews of TASK-74/76/84 have a single reference; the audit log format
  is defined once.
- Tasks: TASK-105 in m-11 (the document can be drafted as soon as TASK-84
  lands).
