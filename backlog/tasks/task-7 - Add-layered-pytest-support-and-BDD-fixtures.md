---
id: TASK-7
title: Add layered pytest support and BDD fixtures
status: In Progress
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-25 02:36'
labels: []
milestone: m-2
dependencies:
  - TASK-2
  - TASK-24
references:
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: high
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provide opt-in test support for pure Python, Qt, initialized QGIS, Desktop plugin, and bridge contract layers. Integrate pytest-bdd for scenario-level behavioral cases without making every test require QGIS.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Pure Python tests run without QGIS installed/importable.
- [ ] #2 QGIS lifecycle and Qt fixtures set up and tear down deterministically and can be selected independently.
- [ ] #3 BDD scenarios can share steps/fixtures with ordinary pytest tests where appropriate.
- [ ] #4 External services and QGIS collaborators can be faked/injected in unit tests.
- [ ] #5 Python bridge fixtures and shared contract vectors cover forged caller identity, denied operations, malformed results, cancellation acknowledgement, expired handles and non-destructive resource release without requiring QGIS for pure cases.
- [ ] #6 Behavioral/property tests cover ordered event/stream sequences, terminal/disposal races and stale-generation delivery using deterministic scheduling; separate real QWebEngine tests verify native caller binding and cleanup rather than treating fakes as integration evidence.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Extend bridge test support for proposed decision-23; TASK-4 owns the TS client/transport harness implementation. Coordinate shared fixtures without forcing Qt/QGIS or browser globals into pure Python imports. No task status or criterion is completed by this documentation update.

Gap audit 2026-10-25 against main 687b925: AC1 largely proven by test_pure_imports and the pip-only macOS/Windows CI, but no layer markers exist so pure vs native cannot be selected explicitly. AC2: every native module (test_jobs_native, test_ui_native, test_webengine_native, test_network_native, services/conftest) repeats its own bindings-path setup, guarded imports and QApplication/QgsApplication fixture; which application class a run gets depends on file order; teardown exists only in services/conftest. AC3: six .feature files already share conftest fixtures with ordinary tests. AC4: qgis_sdk.testing fakes and HostServices injection exist. AC5: cases.json carries not-authorized, invalid-result, cancelled and stale-generation but no forged-identity, expired-handle or non-destructive release vector (those are Python-only unit tests today). AC6: no Hypothesis model of the stream dispatcher (ordering, terminal/disposal races, stale-generation delivery) and no real QWebEngine+QWebChannel test of host-minted caller binding and cleanup; test_webengine_native covers egress policy only. Plan: (1) extend generate_bridge_cases with the three vectors; (2) add a stream state machine; (3) register layer markers and one shared Qt/QGIS application fixture in tests/conftest.py, used by every native module and the services backend; (4) add test_webchannel_native.py; (5) document layer selection in doc-12.

Implemented on arena/cad8133b-qgis-sdk. AC1/AC2: tests/layers.py + tests/conftest.py declare pure, qt, qgis, webengine, desktop and the derived native/pure markers under --strict-markers; session fixtures qt_app/qgis_app/webengine_profile own the one application and profile per process; every native module takes them instead of bootstrapping its own; services native backend is a qgis-marked parameter; tests/test_layers.py checks the selection algebra and runs a pure module with qgis/PyQt6 unimportable in a child interpreter. AC3/AC4: tests/bridge_steps.py (plugin) shares contract_host and the step definitions between features/bridge_contract.feature and test_bridge_contract_fixtures.py, over the fakes only. AC5: generate_bridge_cases.py adds forged-identity, expired-handle and release-borrowed vectors consumed by bridge.test.ts; cases.json rendered byte-identical to biome. AC6: test_bridge_streams_properties.py (Hypothesis state machine, mutation-checked) and test_webchannel_native.py (real page over QWebChannel: host-minted identity answers, pushed frames ordered, dispose closes the source once, page deletion clean). CI native step now runs -m native with QGIS_SDK_NATIVE_SERVICES=1; doc-14 gains a Test layers section. Local gate: lint/format/actionlint/typecheck/biome clean; bun run test 1112 passed/33 skipped; coverage Python 97.12%, bridge 96.49/98.12; tests/scripts 174 passed; -m native 109 passed/7 desktop skipped; full suite with native services 1140 passed/8 skipped.
<!-- SECTION:NOTES:END -->
