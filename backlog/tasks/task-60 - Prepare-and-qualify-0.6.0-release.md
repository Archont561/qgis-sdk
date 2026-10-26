---
id: TASK-60
title: Prepare and qualify 0.6.0 release
status: In Progress
assignee: []
created_date: '2026-10-25 23:27'
updated_date: '2026-10-26 18:42'
labels: []
milestone: m-5
dependencies:
  - TASK-31
  - TASK-58
  - TASK-59
  - TASK-61
  - TASK-62
  - TASK-63
  - TASK-64
  - TASK-65
  - TASK-66
  - TASK-67
priority: high
type: chore
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. 0.6.0 is the API-ergonomics minor (m-5): function-form @job (decision-38, TASK-58) and capability attributes replacing require_<name>() (decision-39, TASK-59), both already on main with doc-12 migration notes. The bridge joined the milestone with TASK-61 (decision-40: root entry barrel, prefixed generated contract errors; wire unchanged), so 0.6.0 is a pair: Python 0.6.0 and @archont561/qgis-sdk 0.4.0. Verify the milestone work with the 0.5.0 gate re-run over the new API plus the bridge gate and obtain explicit release authorization; stamp, tag (python-v0.6.0 and ts-v0.4.0 on the merge commit) and publish only on that authorization, with an -rc.N dry run first if asked.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.6.0 work has verified outcomes and relevant test/artifact evidence: Python suite, tests/scripts, the example project and the opt-in harnesses the two changes touched are green on the gate commit; the doc-12 0.6.0 migration note names every removed or renamed symbol.
- [ ] #2 Use valid SemVer and prereleases such as 0.6.0-rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves to >=0.6.0,<0.7) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a 0.5-style project reports the API changes rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge pair is confirmed with evidence: @archont561/qgis-sdk 0.4.0 (TASK-61, decision-40) is gated with the same run - Bun tests, typecheck, Biome, release.py verify-versions agreeing on contract version 1 in both languages - and stamped and tagged ts-v0.4.0 on the same merge commit only on the same explicit authorization; HOST_FINGERPRINT, HOST_SCHEMA_VERSION and BRIDGE_PROTOCOL_VERSION are shown unchanged since ts-v0.3.0, and the record states that bridge 0.4.0 ran against the 0.6.0 runtime.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
decision-41 (TASK-62): release.py stamp --scope typescript now also rewrites SDK_NPM_VERSION in qgis_sdk_tools/scaffold/web.py, so the ts-v0.4.0 stamp moves the scaffold's bridge pin to 0.4.0 in the same commit; verify-versions reports it as the scaffold pin. Once that pin names 0.4.0, the scaffold templates may import from the root barrel instead of ./bridge.

decisions 42/43 (TASK-63..65) join 0.6.0: function-form algorithms on plugin-owned providers and the generated host artifacts are further 0.x breaking changes of the same minor, so the doc-12 0.6.0 migration note must cover them before this gate runs.

decision-44 (TASK-66) adds QgisSdk.fromBridgeSchema and the typed bridge.schema.ts to the bridge 0.4.0 delta; decision-45 (TASK-67) adds Desktop bindings and surfaces to the Python 0.6.0 delta. Both are wire-neutral; AC #5's fingerprint evidence still applies unchanged.

TASK-66 landed (sprint 2): bridge 0.4.0 carries QgisSdk.fromBridgeSchema, the schema types, the default QWebChannel transport, the schema-driven validator, QgisSdkContractError and QgisSdkWebChannelError in the root, BridgeProvider's qgis prop and useQgisSdk, and the schema-typed harness; Python 0.6.0 carries the dispatcher's handshake answer (kind: "handshake"). Protocol 1, HOST_SCHEMA_VERSION 1 and HOST_FINGERPRINT are unchanged (the host generator's --check is green). The gate's doc-13 check covers the 0.4.0 migration note's before/after main.ts; AC #5's statement that bridge 0.4.0 ran against the 0.6.0 runtime now also means the handshake was answered by a real dispatcher (test_reference_example_native.py, QGIS_SDK_REFERENCE=1).

Gate run 2026-10-26 on main 2763cad (TASK-67 merge, #98); full record in doc-14 '0.6.0 release gate (TASK-60, 2026-10-26)'. Unstamped tree. AC 1 evidence: all nine milestone tasks Done; static gate, bun run test 5/5 (bridge 234, alias 10, page 5, Python 1675/43), coverage 95.58% / 98.55%, tests/scripts 248, twelve opt-in harnesses green (lifecycle 5, desktop adapter 22, coexistence 23, scaffold desktop 10, services smoke 7, scheduler 11, WebEngine 9, services 134, scaffold web 8, devtools 9, bundle 1, reference 5), example check/test/--target qgis clean; AST diff of public names python-v0.5.0..main matched against doc-12's 0.6.0 note (RunSignature/describe_run_method added to it). AC 2: plan --bump minor from python-v0.5.0 -> python-v0.6.0 (5 breaking, 14 features) and from ts-v0.3.0 -> ts-v0.4.0 (2 breaking, 4 features, 1 fix); verify-versions agrees on 0.5.0/0.3.0 and contract 1 on the unstamped tree. AC 3: twine-checked wheels, clean CPython 3.11.2 venv install (60/62 modules QGIS-free, pip check clean, new --ui native/check/test/targets/build from the installed package, ZIP vendoring verified under python -S); 0.5-style project (scaffolded from the python-v0.5.0 worktree) under today's check reports ENTRY002/META001/PROJECT002/VERSION003, no crash. AC 5: HOST_FINGERPRINT sha256:f96bdf10..., HOST_SCHEMA_VERSION 1, BRIDGE_PROTOCOL_VERSION 1 identical at ts-v0.3.0, python-v0.5.0 and main; bridge 0.4.0 from this tree ran against the 0.6.0 runtime in the reference harness's real QWebEngineView. Not run: the Conda build (conda-forge unreachable from the sandbox). AC 4: no approval yet; nothing stamped, tagged or published. ACs stay unchecked until the tag's release.yml run is green.

Release authorised 2026-10-26 ('release' after the gate record merged as #99 -> adc8fa0). Stamp PR on branch arena/7fcf0fef-qgis-sdk: python 0.6.0 (nine manifest entries, tools range >=0.6.0,<0.7, example windows >=0.6,<0.7) and typescript 0.4.0 (package.json, alias, scaffold pin). Stamped tree: static gate clean, bun run test 5/5 (Python 1650/43), tests/scripts 248, wheels twine-clean (kit b6861c99..., runtime 8d5143c4..., tools 10894bf4...), clean CPython 3.11.2 install with pip check clean, scaffold writes the 0.6/0.4 pins. Next: on 'Merge', tag python-v0.6.0 and ts-v0.4.0 (annotated, notes prepared) on the merge commit, watch both release.yml runs, verify PyPI/npm/GitHub Release artifacts, then check ACs.
<!-- SECTION:NOTES:END -->
