---
id: TASK-113
title: >-
  Make bridge.streams the single owner of the stream event vocabulary and the
  event-split seam
status: Done
assignee: []
created_date: '2026-10-27 21:55'
updated_date: '2026-10-27 22:15'
labels: []
milestone: m-7
dependencies: []
priority: low
type: chore
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-10-27 (clean-code core-dry-single-source, core-encapsulation). The three stream event kinds are spelled three times in the runtime: declarations/_contract.py:8 STREAM_EVENT_KINDS, bridge/protocol.py:49 STREAM_EVENT_KINDS (comment: 'streams enumerates the same three'), bridge/streams.py:85-90 StreamEventType. Nothing asserts the three agree - test_bridge_generate.py pins the TypeScript declarations against StreamEventType only - so a fourth kind added to the enum would pass @stream(events=...) validation in one module and be refused by frame validation in another. Separately, ui/streams.py:23 imports the underscore-private _split_event from qgis_sdk.bridge.streams across package lines, so a bridge-internal rename breaks ui. Smallest fix: protocol.py imports STREAM_EVENT_KINDS from qgis_sdk.declarations (bridge already depends on declarations; declarations is the lowest layer that needs the names), a test pins tuple(k.value for k in StreamEventType) == STREAM_EVENT_KINDS, and _split_event gets a public name on bridge.streams (or moves next to the vocabulary) that ui/streams.py imports. Non-goals: no new event kind, no wire or schema change - HOST_FINGERPRINT, CONTRACT_FINGERPRINT and src/generated stay byte-identical.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Exactly one tuple literal spells data/progress/state in packages/qgis-sdk-runtime/src; protocol.py and the declarations share it and a unit test pins StreamEventType to it.
- [x] #2 No module under qgis_sdk/ui imports an underscore-prefixed name from qgis_sdk.bridge (grep 'from qgis_sdk.bridge.* import .*\b_' is empty) and the ui stream tests pass unchanged.
- [x] #3 generate_bridge_clients.py --check passes and both fingerprints are unchanged.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done on the audit branch: declarations/_contract.py is the one tuple; bridge/protocol.py imports it, bridge/streams.py derives _EVENT_KINDS from StreamEventType, ui/streams.py validates emit() kinds against it (a fifth inline spelling the audit missed) and imports the now-public split_event. Three tests in test_bridge_streams.py pin enum == tuple, protocol is declarations, the ui EventKind literal prefix, and the public seam. Python suite 1971 passed / 48 skipped; generate_bridge_clients.py --check up to date; HOST_FINGERPRINT in generated/host.ts unchanged.

Merged in PR #120 (merge commit c4c96f5, 2026-10-27) with CI green on c278dec.
<!-- SECTION:NOTES:END -->
