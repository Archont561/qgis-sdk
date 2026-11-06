---
id: TASK-85
title: >-
  Add the canvas service: extent, scale, CRS, zoom, refresh, map themes, extent
  stream and capture tools
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-06 15:19'
labels: []
milestone: m-9
dependencies:
  - TASK-84
  - TASK-81
type: enhancement
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. Protocol, models, fake, native (QgsMapCanvas on Desktop and in the app window; refuses by name on the server), host operations and grants: canvas.extent/scale/crs/center, zoom_to(layer|selection|extent), refresh, themes.list/apply, on_extent_changed stream; @tool declaration for point/line/polygon capture returning geometry models; bridge manifest regenerated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every operation works against the fake and the native canvas with one contract test set, the extent stream delivers ordered frames, and a capture tool returns the drawn geometry (qgis native tests, offscreen).
- [x] #2 The page reaches canvas.* through qgis.host under a grant, typed in generated/host.ts; HOST_FINGERPRINT moved and the fixtures were regenerated, never hand-edited; the console and agent see the same operations.
- [x] #3 doc-22 row complete; doc-12/doc-13 document the service; the example uses zoom_to after an algorithm.
<!-- AC:END -->

## Implementation notes

Implemented on the 0.10.0 sprint-3 branch, on top of the sprint-2 services.

**Models.** `qgis_sdk.models.canvas` holds QGIS-free value types: `CanvasExtent`
(four finite, ordered numbers and an optional CRS), `CanvasPoint`, `MapThemes`
(names with an `active` entry that is always one of them), `ZoomTarget`
(`layer`/`selection`/`extent` plus a `margin`) and the wire schemas
`CANVAS_EXTENT`, `CANVAS_POINT`, `MAP_THEMES`, `ZOOM_REQUEST`, `CAPTURE_REQUEST`.
A capture answers with the same `Geometry` model a feature does.

**Contract.** `qgis_sdk.services.Canvas` is the Protocol: `extent`, `scale`,
`crs`, `center`, `zoom_to`, `refresh`, `themes`, `apply_theme`,
`capture(shape, on_capture) -> canceller` and
`watch_extent(on_extent) -> canceller`. Capture and the extent stream are
callbacks rather than blocking calls because both wait on a person.

**Fake and native.** `qgis_sdk.testing.FakeCanvas` answers from a box the test
controls and refuses a layer, theme or selection the test never declared.
`adapters/qgis/canvas.py` wraps one `QgsMapCanvas`, installs a `QgsMapTool`
subclass for a capture (replacing the active tool and restoring it afterwards),
follows `extentChanged` for the stream, and refuses every method by name on a
server host, where there is map settings rather than a canvas.

**Where the canvas comes from.** A Desktop host resolves it from
`iface.mapCanvas()`; an app window hands its own widget to the context, so a
graphical app zooms the canvas the user is looking at rather than a second one
the runtime made; a server keeps the capability only to refuse by name. A bare
`QgsApplication` that opened no window has no canvas capability at all, which is
what `ctx.has("canvas")` answers - the alternative was a service that refuses
every call.

**Host surface.** Ten operations behind two grants: `canvas.read` for `extent`,
`scale`, `crs`, `center`, `themes` and the `canvas.extent_changed` stream, and
`canvas.control` for `zoom_to`, `refresh`, `apply_theme` and the
`canvas.capture` stream. `HOST_FINGERPRINT` moved to
`sha256:73e9a9af...` and `generated/host.ts` was regenerated, never hand-edited.

**`@tool`.** `qgis_sdk.declarations.tool` declares an instance method that
receives the drawn geometry; `start(tool, ctx)` asks `ctx.canvas` for the
drawing of the declared shape and runs the body when it arrives, returning the
canceller. The declaration carries no bridge surface - like `@job`, it describes
itself and is not part of `PluginDescription` - so the plugin manifest the page
reads does not move. A binding refuses a tool in either order (`bind an @action
that calls start() on it`), the same rule `@job` and `@stream` follow: the host
places buttons for actions, and a tool it called directly would have no
geometry to run on.

**Evidence.** `tests/services/test_canvas_contract.py` runs the same assertions
against the fake and an offscreen `QgsMapCanvas`;
`tests/services/test_canvas_native.py` adds what only QGIS can answer (encoded
drawings, a real pan reaching the stream, a project theme, the server refusal);
`tests/test_bridge_host.py` covers the ten operations, both streams, both
grants and the host without a canvas; `tests/test_canvas_tools.py` covers the
declaration and the runner. The native half is opt-in with
`QGIS_SDK_NATIVE_SERVICES=1`, so it runs in CI rather than in a QGIS-free
workspace.

**Delivered on PR #164** (`41e5d8d`, 2026-11-06) as sprint 3 of the 0.10.0 train:
`canvas.*` on Desktop and in the app window, `@tool` capture, the extent stream,
and the reference example zooming to an algorithm's output.
