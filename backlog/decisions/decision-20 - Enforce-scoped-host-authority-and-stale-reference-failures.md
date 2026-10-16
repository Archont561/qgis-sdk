---
id: decision-20
title: Enforce scoped host authority and stale reference failures
date: '2026-10-16 09:05'
status: accepted
---
## Context

A broad host bridge (ADR-18) needs concrete resource boundaries. Restricting Python HTTP calls alone does not restrict JavaScript fetch, navigation or embedded resources.

## Decision

Use opaque session-scoped handles for live layers/resources. Validate type, session, existence and permission on each use. Removed layers, foreign/expired handles and replaced runtimes fail explicitly; never silently resolve by matching names. Reconnection reacquires current summaries/handles. Exact session boundaries must be specified consistently with page reload and runtime replacement.

Web views receive filesystem authority through a native picker or explicit plugin grant, with scope for view/session and allowed operation. Do not accept arbitrary frontend paths as authority. Explicit exports require destination/overwrite handling and partial-file cleanup. Canonicalization, symlink/path traversal behavior and grant revocation need security tests.

Per-view host networking restricts destination origins, methods and use of host authentication; validate redirects and private-network access policy and redact credentials. A grant must not become unrestricted fetch. Define request/body limits and permission syntax through further engineering work.

Production WebEngine views also enforce navigation/resource-network restrictions, not just host HTTP authorization. Packaged assets and explicit external origins are the default boundary; local frontend/HMR origins are explicit development exceptions. Qualify the concrete browser controls, redirects, frames, resource requests and page reload behavior on supported Qt/Chromium versions. Do not describe host-only checks as complete egress control or claim a security sandbox without evidence.

## Consequences

- File grants, network grants, browser controls and handle validation are distinct enforcement layers.
- Tests cover stale/foreign handles, denied/redirected destinations, expired grants, filesystem escapes and browser requests bypassing the host API.
- The permission/resource inventory and browser enforcement mechanism remain implementation work; no security guarantee is inferred from declarations alone.
