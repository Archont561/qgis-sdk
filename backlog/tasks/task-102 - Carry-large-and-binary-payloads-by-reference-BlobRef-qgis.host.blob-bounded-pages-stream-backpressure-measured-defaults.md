---
id: TASK-102
title: >-
  Carry large and binary payloads by reference: BlobRef, qgis.host.blob, bounded
  pages, stream backpressure, measured defaults
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
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
- [ ] #1 A result above the cap returns a BlobRef the page fetches with the right checksum and that is released with its view; an over-size page request is refused by name; the fakes and the native host share the tests (pure + webengine tests).
- [ ] #2 A fast producer stream coalesces frames until ack, sequence numbers are contiguous, and a consumer gap triggers a re-subscribe (stateful tests on the fakes, one native run).
- [ ] #3 The inline cap and page defaults are measured in a QWebEngineView with timings recorded in decision-59's status review; the protocol minor and fingerprint move are shown by verify-versions; doc-13 documents BlobRef and ack.
<!-- AC:END -->
