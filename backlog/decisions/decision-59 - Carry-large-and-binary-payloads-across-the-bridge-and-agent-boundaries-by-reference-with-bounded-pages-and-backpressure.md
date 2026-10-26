---
id: decision-59
title: Carry large and binary payloads across the bridge and agent boundaries by reference, with bounded pages and backpressure
date: '2026-10-26'
status: accepted
---
## Context

decision-54 brings features, geometries, rasters, point clouds and layout
exports to the page, the console and agents. `QWebChannel` is a JSON
channel; the agent transport is JSON envelopes over loopback; neither was
designed for megabytes. decision-54 deferred the wire-model questions to
TASK-86's status review; that is a design, not a decision, and the rest of
the services batch would build on whatever TASK-86 improvised.

## Decision

1. **Small inline, large by reference.** A payload up to an inline cap
   (default 256 KiB per message, configurable per host operation) travels
   inline: geometry as WKT/GeoJSON by default, WKB as base64 when asked.
   Above the cap the operation returns a `BlobRef` (id, size, media type,
   checksum, expiry) and the client fetches bytes through
   `qgis.host.blob(ref)` - on the page over a loopback blob endpoint that
   the runtime's agent transport already provides (same token, same
   `Origin` check, decision-49), on the agent side as a resource. Files
   stay `FileRef` (decision-20); a `BlobRef` is a transient owned by the
   view scope and is released with it.
2. **Paging is mandatory for iteration.** `features.iterate` and every
   list that can exceed the cap take `page=` and return a cursor; the
   host enforces a maximum page size (default 1000 features) and refuses
   larger requests by name. No operation returns an unbounded array.
3. **Streams have backpressure.** A stream that can outrun its consumer
   (features, progress at high rate, extent changes) delivers frames
   only after the previous frame's `ack`, coalescing when the producer is
   faster; the fakes test the coalescing rule. Frames carry sequence
   numbers; a consumer that detects a gap re-subscribes.
4. **Rasters and point clouds never move whole.** `rasters.sample`,
   `statistics` and tiled `read(extent, size)` return bounded arrays; an
   export is a job that produces a `FileRef`. Same for point clouds and
   layouts.
5. **Measured, not guessed.** TASK-102 measures the inline cap and page
   defaults in a real `QWebEngineView` and records them in the decision's
   status review; the numbers above are the starting values.

## Consequences

- One blob mechanism serves page and agent; the bridge gains `BlobRef`
  and `qgis.host.blob` (a host manifest change, so a bridge minor in
  0.10.0 as already planned).
- `HOST_FINGERPRINT` moves with the manifest; the wire protocol gains
  `ack`, a protocol minor (`BRIDGE_PROTOCOL_VERSION` moves once).
- Tasks: TASK-102 in m-9 before TASK-86, which depends on it.
