---
id: decision-40
title: Make the root entry the page import and keep generated plugin clients import-free
date: '2026-10-26 12:00'
status: accepted
---
## Context

An ergonomic review of `@archont561/qgis-sdk` at `ts-v0.3.0` found the root
entry almost empty of what a page needs. It exported the plugin-description
parser, the error root and two helpers (`isPlainRecord`, `isSafeJsonInteger`)
that `./bridge` and `./react` imported *from the root* because the modules had
nowhere else to share them; `BridgeClient` lived only behind `./bridge`. The
only real consumer in the repository (`examples/simple/web`) and the README's
quick start imported nothing from the root. Two error classes -
`QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError` - mirrored
Python errors that nothing in the package ever raised: a Python fault reaches
a page as `QgisSdkBridgeRemoteError` carrying the code. `StreamEventKind` was
declared twice. And the package had three error roots: `QgisSdkError`, plus
`HostContractError extends Error` in the generated `./host` module and
`ContractError extends Error` in every generated plugin client - the only
SDK-defined exceptions without the `QgisSdk` prefix the repository rules
require, and the ones a page is most likely to hit during development yet
could not catch through `instanceof QgisSdkError` or match by `code`.

The subpath split itself was right and tested: `./react` needs an optional
peer, `./testing` is a development dependency, and `surface.test.ts` proves
the neutral entries load neither.

## Decision

1. **The root is a barrel.** `index.ts` is `export *` over three modules:
   `./errors` (`QgisSdkError` alone, so every entry shares one root without
   importing each other), `./declarations` (the version 1 plugin-description
   contract and its wire limits) and `./bridge`. `./bridge` stays as a
   subpath for existing imports. `./host`, `./react` and `./testing` remain
   subpath-only for the reasons above.
2. **No internal helper is public.** `isPlainRecord` and the stream event kind
   list move to an unexported `./internal`; `StreamEventKind` is declared
   once, in `./declarations`, and the frame parser imports the same list. A
   test pins the root to the union of the three modules and refuses the
   internal names.
3. **No idle mirror of a Python-only error.** The two unused classes are
   removed. The uniform contract across both languages is the wire `code`
   (`scope_closed`, `unsupported_capability`, ...), reached on
   `QgisSdkBridgeRemoteError.code`; class names are not part of it
   (AGENTS.md).
4. **Generated contract errors carry the prefix and the code.** The host
   module ships inside the package, so `QgisSdkHostContractError extends
   QgisSdkError` through one relative import of `./errors`, with
   `code = "contract_validation_failed"` - the code
   `QgisSdkContractValidationError` already uses for the same category in
   both languages. A plugin's generated module **stays import-free**:
   `QgisSdkContractError extends Error` and carries the same `code`.

The plugin client stays import-free because the alternative has two real
costs and one small benefit. An `import { QgisSdkError } from
"@archont561/qgis-sdk"` hardcodes one of the package's two npm names - a page
that installed the unscoped alias `qgis-sdk` would resolve it only through
hoisting, and not at all under a strict package manager - and it couples a
file emitted by `qgis-sdk-tools` X to the npm package Y that must be
installed beside it, a pairing no gate currently checks. The benefit, one
`instanceof` catching both errors, is already served by `code`, which is the
identity the repository's error rule names as stable. The host module has
neither cost: its import is relative and it is versioned with the file it
imports.

## Consequences

- `@archont561/qgis-sdk` gets a minor (`0.4.0`, breaking in 0.x per
  decision-25): the root re-exports `./bridge`; `QgisSdkScopeClosedError`,
  `QgisSdkUnsupportedCapabilityError` and `isPlainRecord` leave the root;
  `./host` exports `QgisSdkHostContractError` instead of `HostContractError`.
  Nothing on the wire changes: `BRIDGE_PROTOCOL_VERSION`,
  `PLUGIN_DESCRIPTION_SCHEMA_VERSION`, `HOST_SCHEMA_VERSION` and
  `HOST_FINGERPRINT` (a hash of the contract, not of the text) are all
  unchanged. doc-13's 0.4.0 migration notes list the renames.
- `qgis-sdk-tools` emits `QgisSdkContractError` instead of `ContractError`
  from `0.6.0`; a plugin regenerates with `qgis-sdk bridge generate` and
  renames the class in its `catch` clauses, or better, matches on `code`.
  doc-12's 0.6.0 migration notes carry the entry.
- The 0.6.0 milestone (m-5) loses its "bridge is a bystander" premise: the
  pair becomes Python `0.6.0` + bridge `0.4.0`, and TASK-60's bridge
  criterion changes from "no file changed" to "the paired bridge release is
  gated and stamped with it". The host wire is unchanged, so the contract
  check `release.py verify-versions` keeps agreeing at `1`.
- The generator's `_Surface` gains `error_base` and `imports`; the
  reserved-name check now also refuses `QgisSdkError` and `Error` as a
  declared type name.
- Not changed: `./host` stays out of the root. If a later review finds most
  pages import both, folding it in is additive and needs no new decision.
