---
id: decision-56
title: Define 1.0 API stability as tiers with a generated public API inventory and a one-minor deprecation window
date: '2026-10-26'
status: accepted
---
## Context

Every milestone says "stable 1.0.0 requires a later explicit API-stability
decision" and none says what stability would cover. Without it, 1.0 is a
number. decision-25 versions each package independently behind a shared
contract version; decision-22 keeps contracts experimental; doc-12 carries
migration notes per minor by hand.

## Decision

1. **Three tiers, named per symbol.** *Stable*: `qgis_sdk` declarations
   (`@plugin`, `@action`, `@job`, `@stream`, bindings, surfaces,
   `providers`/`surfaces`), the context classes and service Protocols,
   the models, the `qgis_sdk.ui` catalogue's public names and constructor
   keywords, `qgis_sdk.testing` fakes and fixtures, `[tool.qgis-sdk]`
   tables, CLI commands and flags, check rule ids and their meaning, the
   bridge wire protocol and the generated client's public API, the host
   manifest names. *Evolving*: `qgis.host` operation sets (additive within
   a minor), the agent tool surface, `dev.*` tools, `release.py`.
   *Internal*: `adapters/`, `bridge/` internals, `core/`, anything
   underscored. Tier is declared in code (`__stability__` on modules and
   `@stable`/`@evolving` marks where a module mixes) and rendered in
   doc-12.
2. **A generated inventory is the contract.** `qgis-sdk api dump` writes
   the public API (names, signatures, model fields, CLI, rule ids, host
   operations, catalogue) as JSON; `release.py verify-api` diffs it against
   the last tag and classifies each change as additive, deprecating or
   breaking; a breaking change in a *stable* symbol after 1.0 requires a
   major and a `BREAKING CHANGE` footer, before 1.0 a documented minor.
3. **Deprecation window.** `@deprecated(since=, removal=, use=)` on Python
   symbols and `@deprecated` JSDoc on TypeScript; a deprecated use is a
   `check` finding `API001` naming the replacement and the removal
   version; removal no earlier than the next major (after 1.0) or the
   second following minor (before 1.0). Rule ids are never reused.
4. **Support window per package.** The latest major receives features;
   the previous major receives fixes for twelve months after the next
   major's first release. Pre-1.0 minors receive nothing after the next
   minor.
5. **The 1.0 gate.** 1.0.0 ships only when: the inventory exists and is
   tracked, every stable symbol has a tier mark, doc-22 is complete or
   out of scope by decision, the support matrix of decision-57 has its
   Windows row qualified, and the deprecation sweep (TASK-98) removed or
   marked every pre-1.0 leftover.

## Consequences

- doc-12 gains a "Stability" section rendered from the inventory; the
  README promises nothing beyond it.
- Tasks: TASK-97 (tiers, `api dump`, `verify-api`, `@deprecated`,
  API001), TASK-98 (freeze review and sweep), gate TASK-107 in m-11.
