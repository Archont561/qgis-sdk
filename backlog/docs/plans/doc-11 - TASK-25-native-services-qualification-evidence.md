---
id: doc-11
title: TASK-25 native services qualification evidence
type: guide
created_date: '2026-10-24 15:20'
---
# TASK-25 native services qualification evidence

**Scope of the claim.** This records one headless run of the curated native
services on Linux x86-64. It proves the service contracts against a real QGIS
host. It does **not** qualify a Desktop GUI, a canvas or 3D view, Windows or
macOS, or any rendering a user would see: `QT_QPA_PLATFORM=offscreen` shows no
window and paints nothing. Those targets remain open and are tracked by
[TASK-33](../../tasks/task-33%20-%20Qualify-Windows-macOS-and-Desktop-QGIS-targets.md),
whose AC #1 (clean Windows QGIS installation) and AC #2 (Desktop GUI path) are
still unchecked.

## Environment

| Item | Value |
| --- | --- |
| QGIS | `4.2.3-Belém do Pará` |
| Qt | `6.11.2` (PyQt6) |
| Python | `3.14.8` |
| Platform | `Linux-6.1.158+-x86_64-with-glibc2.36` |
| Qt platform plugin | `offscreen` |
| Prefix | the Pixi `default` environment (`.pixi/envs/default`) |

## Command and result

```sh
pixi run -e default python packages/qgis-sdk/scripts/native_services_smoke.py
# exit 0
```

The full report, verbatim (key order as printed; `\u00e9` in the JSON is `é`):

```json
{
  "error": null,
  "layer_crs": "EPSG:4326",
  "layer_field_names": ["id", "value"],
  "layer_geometry_type": "point",
  "layer_name": "points",
  "layer_opened": true,
  "notification_delivered": true,
  "notification_refused_after_close": true,
  "passed": true,
  "platform": "Linux-6.1.158+-x86_64-with-glibc2.36",
  "project_layer_ids": ["points_2dcedacf_a49a_4447_8bbc_9bcd519261a6"],
  "python_version": "3.14.8",
  "qgis_exited": true,
  "qgis_initialised": true,
  "qgis_version": "4.2.3-Belém do Pará",
  "qt_version": "6.11.2",
  "reads_refused_after_close": true,
  "scope_closed": true,
  "selection": [1, 3],
  "settings_refused_after_close": true,
  "settings_round_trip": true,
  "style_applied": true,
  "style_incompatible_refused": true,
  "theme_unchanged": true
}
```

The layer id contains a runtime-assigned UUID and changes every run; every other
value above is stable.

## What each stage proves

| Stage | Proves |
| --- | --- |
| `qgis_initialised` / `qgis_exited` | a real `QgsApplication` started and shut down cleanly |
| `layer_opened`, `layer_name`, `layer_geometry_type`, `layer_field_names`, `layer_crs` | OGR opened the fixture as the `points` layer with fields `(id, value)` reported as `EPSG:4326`, through the QGIS-free `VectorLayerInfo` |
| `selection` = `[1, 3]` | a selection made through QGIS (`QgsProject` + `selectByIds`) is readable through the contract, which never sets a selection |
| `project_layer_ids` | the output layer was added to the project once, by an explicit call, after the layer existed |
| `scope_closed`, `reads_refused_after_close` | closing the owner scope released the layers and every later read raised `QgisSdkScopeClosedError`; a repeated close is a no-op |
| `settings_round_trip`, `settings_refused_after_close` | `QgsSettings` read/write under the adapter's prefix, and refusal after close |
| `notification_delivered`, `notification_refused_after_close` | a message reached an injected sink, and a closed scope refuses further messages |
| `style_applied`, `style_incompatible_refused` | the packaged QML loaded onto the layer, and a line style was refused on a point layer before anything was applied |
| `theme_unchanged` | the application stylesheet and six palette roles were identical before and after the style application |

## What this run cannot prove

1. **Anything visual.** No display server, so no window, canvas, 3D view, dock,
   menu or in-Desktop `QWebEngineView`. `offscreen` renders nothing.
2. **A real Desktop `iface`.** The harness runs headless, as TASK-24's lifecycle
   harness does; `iface` interaction is unexercised here.
3. **Windows or macOS.** No non-Linux host is available, and CI's `cross-platform`
   job installs the QGIS-free package with `pip`, not QGIS.
4. **The default message-log sink's content.** `NativeNotifications` without an
   injected sink writes to `QgsMessageLog`, which QGIS routes through its own
   handler; that swallows Python stdout, so this run proves the call executes
   without raising, not what appeared in the log panel. Delivery itself is proven
   only through the injected sink.
5. **Real Processing outputs.** TASK-25 produces no algorithm output; output
   ownership across a real Processing run is TASK-14's evidence, not this one.
6. **Style rendering fidelity.** That the packaged QML parsed and applied is
   proven; that the symbols look right is not, and cannot be, headless.

## Repeated in the suite

- Contract parity, both backends: `QGIS_SDK_NATIVE_SERVICES=1 pytest tests/services`
  runs the same contract tests against the fakes and the native adapters (74 tests
  at the time of writing); the three theme assertions live in
  `tests/services/test_native_styles_theme.py` and skip without the flag.
- Harness end to end: `QGIS_SDK_NATIVE_SERVICES_SMOKE=1 pytest tests/scripts/test_qualification_native_services.py`.
- Unusable host: the same module runs the script against a prefix with no QGIS and
  asserts a serialisable report with an error and exit code 1, so a broken
  environment answers instead of skipping silently.
- Coverage: `qgis_sdk/adapters/qgis/*` is omitted from the QGIS-free coverage job
  with the reason stated in `.coveragerc`; it is measured here and in the parity
  suite instead.

## Related

- [TASK-25](../../tasks/task-25%20-%20Implement-curated-native-services-and-packaged-style-support.md) and its slices TASK-25.1–25.5.
- [doc-9](doc-9%20-%20V2-sprint-train-and-0.2.0-dependency-order.md) — sprint order.
- [decision-19](../../decisions/decision-19%20-%20Prove-a-non-destructive-local-GIS-reference-workflow.md), [decision-20](../../decisions/decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md), [decision-16](../../decisions/decision-16%20-%20Separate-reusable-layer-styles-from-UI-themes.md).
