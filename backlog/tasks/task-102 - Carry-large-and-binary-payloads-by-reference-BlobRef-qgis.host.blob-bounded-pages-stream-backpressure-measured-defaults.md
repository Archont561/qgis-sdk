---
id: TASK-102
title: >-
  Carry large and binary payloads by reference: BlobRef, qgis.host.blob, bounded
  pages, stream backpressure, measured defaults
status: In Progress
assignee: []
created_date: '2026-10-26T11:13:00Z'
updated_date: '2026-11-06 15:19'
labels: []
milestone: m-9
dependencies:
  - TASK-84
  - TASK-74
type: enhancement
ordinal: 102000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-59. Inline cap per host operation (default 256 KiB), BlobRef (id, size, media type, checksum, expiry) owned by the view scope, qgis.host.blob(ref) fetching bytes over the loopback blob endpoint of the agent transport (same token and Origin check) and as an agent resource; page= cursors with a maximum page size (default 1000) refused above; stream ack with coalescing and sequence numbers; rasters/point clouds/layouts never move whole; defaults measured in a real QWebEngineView and recorded in decision-59's status review; BRIDGE_PROTOCOL_VERSION moves once for ack; manifest regenerated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A result above the cap returns a BlobRef the page fetches with the right checksum and that is released with its view; an over-size page request is refused by name; the fakes and the native host share the tests (pure + webengine tests).
- [x] #2 A fast producer stream coalesces frames until ack, sequence numbers are contiguous, and a consumer gap triggers a re-subscribe (stateful tests on the fakes, one native run).
- [ ] #3 The inline cap and page defaults are measured in a QWebEngineView with timings recorded in decision-59's status review; the protocol minor and fingerprint move are shown by verify-versions; doc-13 documents BlobRef and ack. **Half done:** doc-13 documents `BlobRef`, the blob fetch, bounded pages and `ack`, and the protocol minor moved with them (`BRIDGE_PROTOCOL_VERSION` 2). The measurement is not recorded and decision-59 has no status review yet, so this criterion is what keeps the task open.
<!-- AC:END -->

**Delivered on PR #163** (`be62853`, 2026-10-31) as the first half of sprint 2:
`BlobRef` and the view-owned blob store, `qgis.host.blob` over the loopback blob
endpoint, `page=` cursors with a maximum page size, and stream `ack` with
coalescing and sequence numbers. Everything except AC 3's measurement is in; the
starting values decision-59 declared (256 KiB inline cap, 1000-item pages) have
not been measured in a real `QWebEngineView`, and the decision has no status
review to record the timings in. Measuring them is the rest of this task, not a
new one.
