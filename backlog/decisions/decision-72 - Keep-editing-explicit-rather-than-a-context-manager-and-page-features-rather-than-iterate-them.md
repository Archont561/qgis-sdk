---
id: decision-72
title: Keep editing explicit rather than a context manager, and page features rather than iterate them
date: '2026-10-31'
status: accepted
---
## Context

decision-54 point 3 asks for editing as an explicit session and for features to be
read in bounded pages, and TASK-86 AC #4 and AC #5 ask for two judgements on top
of that: whether a Python context manager should sit beside the explicit session,
and what a Pythonic feature, geometry-part and vertex iteration would mean here.

The temptations are real. `with ctx.features.edit("parcels") as session:` reads
better than five calls, and `for feature in ctx.features.iter_features("parcels")`
is the shape a Python author expects. Both also hide a decision the caller has to
make knowingly, and both have to answer under a bridge where the consumer may be a
page, a console or an agent on the other side of a message.

## Decision

1. **The explicit session is the API; there is no context manager in 0.10.0.** A
   `with` block would have to answer, in one line of syntax: what a second
   `begin_edit` on a layer already being edited means (the native adapter and the
   fake both return the open session, so a nested `with` would silently share a
   buffer); what a commit that raises does on exit; what cancellation mid-block
   does to the buffer; what a scope closing while the block runs does; whether
   undo goes with the session or with the layer; and what happens to concurrent
   changes another client committed while the block was open. Each has a
   defensible answer, the answers disagree, and a context manager that picks one
   makes the choice invisible at the call site. `commit()`/`rollback()` are two
   statements a reader can see.
2. **A session belongs to the view (bridge) or to the scope (Python), never to a
   `with` block.** On the bridge, disposing the view closes every session it
   began, and a session id from another view is refused as `unknown_handle`.
   In Python, the session is registered on the caller's `ResourceScope`. That is
   the only lifetime the SDK can enforce; a block-scoped lifetime would be a
   second, weaker one.
3. **No `iter_features()` generator.** A generator holds the provider open
   between two statements, cannot be resumed by another message and gives a host
   nowhere to apply a page ceiling. Paging over an explicit cursor is the
   iterator: `page(layer_id, FeatureQuery(limit=100, cursor=...))` is bounded,
   resumable by a later call or a different process, and its `truncated` and
   `next_cursor` say exactly how much is left.
4. **Geometry parts and vertices are counts and encoded payloads, not iterators.**
   `Geometry` carries `geometry_type`, `crs`, `part_count`, `vertex_count` and
   `is_empty`, and the payload in the encoding asked for. A page that needs the
   coordinates decodes the WKB, WKT or GeoJSON it already has; the SDK does not
   project part and vertex objects into its own models in 0.10.0, because each
   would need a model of its own and a wire shape with bounded paging, and
   nothing in the 0.10.0 tasks asks for it. Asking for a part index or a vertex
   index is therefore not a supported form and there is nothing to refuse - the
   API does not have the parameter.
5. **The comparison with native QGIS is recorded, not imitated.** QGIS offers
   `QgsVectorLayer.getFeatures(QgsFeatureRequest)` returning a `QgsFeatureIterator`
   that must be closed or exhausted, and `QgsGeometry.parts()` /
   `QgsGeometry.vertices()` as read-only Java-style iterators over an in-memory
   geometry (SIP also exposes `QgsAbstractGeometry`'s STL iterators to C++ only).
   All three are cheap to start, unbounded in memory and valid only while the
   layer is open on the calling thread. A page is the same idea with the ceiling
   and the cursor made part of the contract.

## Consequences

- The bridge protocol does not change: no `editing.context` operation, no
  streaming of vertices. Sessions and pages are what decision-54 already said.
- A convenience wrapper can arrive later as a purely additive Python API over
  `begin_edit`/`commit`/`rollback` without moving `HOST_FINGERPRINT`, provided it
  answers the six questions above in one documented way.
- A consumer that wants a lazy iterator writes the loop over `page(...)`; the
  fake and the native adapter answer the same loop, so the test is shared.
- Adding part or vertex accessors later is additive on the model (`Geometry`
  gains no wire field until a task needs it) and would be a bridge minor.
- Docs: [doc-12](../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md)
  has the supported forms and the refusals;
  [doc-13](../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md)
  has the page stream a view sees;
  [doc-22](../docs/plans/doc-22%20-%20Service-coverage-map.md) has the rows.
  Task: [TASK-86](../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md).
