---
id: TASK-49
title: >-
  Share one declaration-describer and a Description protocol across plugin,
  algorithm and job
status: Done
assignee: []
created_date: '2026-10-25T01:08:00Z'
updated_date: '2026-10-25 01:26'
labels:
  - refactor
milestone: m-2
dependencies:
  - TASK-15
  - TASK-39
priority: medium
type: enhancement
ordinal: 49000
---

> **Later amendment:** [decision-66](../decisions/decision-66%20-%20Unify-declaration-introspection-with-describe-and-declaration-methods.md) adds `.describe()` to decorated targets. This task records the original no-method constraint; bridge serialization and narrow helpers remain compatible.

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Behaviour-preserving consolidation, found by the 2026-10-25 duplication scan of both packages (core-dry-single-source, core-dry-extraction, core-encapsulation). Author classes stay plain: decision-6 forbids injected base classes or methods and decision-10 forbids a generator-specific base class, so this is NOT a mixin or a to_description method on decorated classes - the shared thing is a describer and a protocol on the description side.

Evidence (Python, packages/qgis-sdk-python/src/qgis_sdk):
- describe_algorithm (algorithms.py:120-168) and describe_job (jobs.py:174-208) are the same body: marker check, _Metadata check, own run method, (self, inputs) arity, _hints, two annotations, two _schema calls. A normalised diff leaves 28 differing lines, all renames plus the asynchronous flag. They also hand-roll the self check that declarations._require_self_first already implements.
- AlgorithmDescription (algorithms.py:87-117) and JobDescription (jobs.py:138-171) are the same dataclass and the same to_dict, differing only by asynchronous.
- The decorators plugin (declarations.py:57), algorithm (algorithms.py:70), job (jobs.py:121) and provider.algorithm (providers.py:195) repeat the same marker pattern: isclass check, duplicate check, setattr of a _Metadata.
- _type_name is defined twice (algorithms.py:65, jobs.py:84). The inputs isinstance refusal text is built twice (algorithms.invoke:206, jobs._submit:811).
- algorithms.py, jobs.py and providers.py import _hints, _metadata, _Metadata and _schema privately from declarations: three modules depend on names that are not part of declarations' contract.
- Canonical JSON (sort_keys, compact separators, allow_nan=False) is spelled out in PluginDescription.to_json (declarations.py:188) and again in bridge/generate.py:235; ActionDescription/StreamDescription.to_dict use a json round-trip idiom twice. bridge/generate._as_mapping (generate.py:441) duck-types hasattr(description, 'to_dict') because no Description protocol names that shape.

Evidence (TypeScript, packages/qgis-sdk-typescript/src): hand-written duplication is small - isPlainRecord is defined in index.ts:168 and bridge.ts:208 and inlined again in react.ts:265. src/generated/host.ts carries its own isRecord/isSafeInteger by design (the generated module imports nothing from the SDK); that is the generator's choice, not duplication to remove. The DECLARATION_ID_PATTERN / validateNonBlankTitle pair mirrors Python _metadata on purpose as two halves of one contract and stays.

Non-goals: no base class, mixin, metaclass or method added to author classes; no change to any to_dict wire shape, schema_version, HOST_FINGERPRINT or generated artifact; describe_plugin/describe_algorithm/describe_job keep their names and concrete return types; the generated TypeScript stays import-free.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 declarations exposes one small internal describer surface (for example describe_run_method(cls, marker, kind) plus the metadata/schema helpers under non-underscore names) and algorithms.py, jobs.py and providers.py import only public names from declarations; describe_algorithm and describe_job are thin calls into it with the same error messages as today.
- [x] #2 A Description Protocol (id, title, schema_version, to_dict, to_json) lives in declarations; PluginDescription, AlgorithmDescription, JobDescription and ProviderDescription satisfy it, to_json is implemented once with the canonical JSON options, bridge/generate reuses that canonical dumper and _as_mapping checks the protocol instead of hasattr.
- [x] #3 One describe(cls) -> Description entry point dispatches on the decorator marker and raises the same QgisSdkDeclarationError text for an undecorated class; a shared declare(marker, decorator_name) builds the four marker decorators so the isclass/duplicate/setattr pattern exists once; _type_name exists once.
- [x] #4 Behaviour is unchanged: every existing test in tests/test_declarations*.py, test_algorithms*.py, test_jobs*.py, test_providers*.py, tests/scripts/test_contract_generation.py and the bridge contract vectors passes without modification; generate_bridge_clients.py --check reports no drift; package coverage gate holds.
- [x] #5 TypeScript: one isPlainRecord in src/index.ts is imported by bridge.ts and react.ts (surface.test.ts still proves index/bridge/host stay free of framework and browser-global imports); src/generated/host.ts is untouched.
- [x] #6 doc-12 names describe() and the Description protocol in the pure-contract table and keeps the sentence that decorators attach metadata without wrapping the class.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in PR #61. declarations.py now owns Metadata/metadata, mark_class/declare_class/declared_metadata, resolve_hints/schema_for, RunSignature + describe_run_method(cls, attribute, kind), type_name, canonical_json, the runtime-checkable Description protocol, and describe(cls) over a register_describer registry (each decorating module registers its marker on import, so declarations never imports a higher layer and test_pure_imports holds). @plugin/@algorithm/@job are one-liners over declare_class; describe_algorithm/describe_job build their concrete description from describe_run_method with the pinned error texts; Algorithm/Job/ProviderDescription gained to_json via canonical_json; bridge/generate.py uses canonical_json for the fingerprint and isinstance(Description) in _as_mapping. TS: isPlainRecord exported once from src/index.ts and imported by bridge.ts and react.ts (stableKey). doc-12 gained a declarations row naming describe() and Description. New tests: packages/qgis-sdk-python/tests/test_describe.py (12) and an isPlainRecord case in tests/index.test.ts. Gate: Python suite 1065 passed/33 skipped, tests/scripts 174 passed, ruff lint+format clean, biome-check clean, typecheck clean, bun test green, coverage Python 97.10% / bridge 96.49% lines, generate_bridge_clients.py --check: no drift.

Closed with PR #61 (CI: checks, macos, windows all green). Behaviour unchanged: existing declaration/algorithm/job/provider tests, contract vectors and generated artifacts pass unmodified.
<!-- SECTION:NOTES:END -->
