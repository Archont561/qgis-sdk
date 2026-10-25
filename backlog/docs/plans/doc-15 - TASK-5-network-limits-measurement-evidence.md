---
id: doc-15
title: TASK-5 network limits measurement evidence
type: other
created_date: '2026-10-24 22:30'
---

# TASK-5 — redirect limit and buffered body ceiling, measured

[decision-4](../../decisions/decision-4%20-%20QGIS-aware-networking-uses-an-async-first-transport.md)
fixed the networking API but left two numbers to
[TASK-5](../../tasks/task-5%20-%20Add-a-QGIS-aware-HTTP-client-and-typed-GIS-service-layer.md)
"from measurement, not from the decision": how many redirects a request may
follow, and how large a fully buffered body may be before the client refuses
it. This document is the measurement, the numbers it produced, and one finding
that changed the transport's shape.

## The harness

`packages/qgis-sdk-python/scripts/network_limits_probe.py` starts a headless
`QgsApplication`, two loopback `http.server` origins on different ports, and
drives `QgsNetworkAccessManager.instance()` on the GUI thread with
`processEvents()`. It prints one JSON report and is deterministic in what it
asks, not in the milliseconds it gets back:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/network_limits_probe.py
```

Three questions, in order:

1. **What does the manager do with redirects on its own?** Request a chain of
   60 same-origin hops with the manager's default policy, count how many it
   follows unaided, then send one request carrying `Authorization`, `Cookie`
   and a custom header through a redirect to the *other* port and record which
   headers the second origin received.
2. **What does a hop cost when the transport follows it?** Issue 20 redirects
   one request at a time with `ManualRedirectPolicy` and take the mean.
3. **What does buffering a body cost the GUI thread?** Download 1, 4, 8, 16,
   32, 64 and 128 MiB bodies; for each, measure the longest gap between two
   consecutive `processEvents()` turns while the reply is in flight (the
   *worst stall*), the gap that contains `finished` plus `readAll()` and the
   conversion to `bytes` (the *finish stall*), and the resident-set delta.

`recommend(redirects, bodies, stall_budget_ms=40)` turns the report into the
two numbers; the 40 ms budget is the one
[doc-6](doc-6%20-%20TASK-13-Qt-scheduler-spike-evidence.md) adopted for one
GUI-thread turn. `tests/scripts/test_network_limits_probe.py` pins the
recommendation logic without QGIS.

## Environment

Linux sandbox and CI runner, Pixi `default` environment: QGIS 4.2.3, Qt 6.11.2,
PyQt6, CPython 3.14.8, `QT_QPA_PLATFORM=offscreen`, loopback only. macOS and
Windows were not measured (no QGIS prefix there, see
[doc-14](../guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)).

## Results

Four consecutive runs on 2026-10-24.

### Redirects

| Measurement | Result |
| :-- | :-- |
| Default manager policy | `NoLessSafeRedirectPolicy` |
| Hops followed unaided | 50, then `TooManyRedirectsError` |
| `setMaximumRedirectsAllowed(10)` | honoured (10 hops) |
| Headers forwarded to the other origin | **`Authorization`, `Cookie`** and the custom header |
| Cost of one transport-followed hop | 0.66–1.18 ms mean (0.71 ms in the final run); the manager's own hop is ≈0.4 ms |

### Buffered bodies

Final run; the ranges in brackets are the spread across all four runs.

| Body | Finish stall ms | Worst stall ms | Transfer ms | Resident delta MiB |
| --: | --: | --: | --: | --: |
| 1 MiB | 0.25 [0.25–0.6] | 1.1 [1.1–1.9] | 2.9 | 5.9 |
| 4 MiB | 1.0 [1.0–1.7] | 3.8 [3.8–6.3] | 8.2 | 11.4 |
| 8 MiB | 2.3 [2.3–3.5] | 6.6 [6.6–11] | 17.4 | 20.8 |
| 16 MiB | 12.9 [12.9–14.5] | 14.0 [14.0–18.5] | 27.0 | 24.5 |
| 32 MiB | 39.9 [39.9–44] | 43.2 [43.2–52] | 43.3 | 83.4 |
| 64 MiB | 78.4 [78.4–83] | 80.6 [80.6–91] | 72.8 | 105.0 |
| 128 MiB | 166 [157–184] | 169 [169–196] | 154 | 174.8 |

The finish stall is the number that matters: it is the single uninterruptible
turn in which Qt hands over the whole buffer and Python copies it. Transfer
time is spread over many turns and does not block the GUI.

## The numbers

- **`DEFAULT_MAX_REDIRECTS = 20`.** Twenty transport-followed hops cost
  14–24 ms in total, inside one 40 ms turn even when every hop is a round trip
  to loopback, so the budget does not force a smaller number and the browser
  convention applies: Chromium and Firefox stop at 20, `requests` at 30, Qt and
  curl at 50. Twenty is the smallest limit a real service is known to live
  with.
- **`DEFAULT_MAX_BODY_BYTES = 16 MiB`.** 32 MiB straddles the budget: its
  finish stall was 39.9 ms in one run and 42–44 ms in the other three, so
  `recommend()` itself flipped between 32 and 16 MiB across runs. 16 MiB
  stalls for 13–15 ms with a worst turn under 19 ms, which leaves room for the
  scheduler tick and the caller's own `json()` on the same turn. Anything
  larger is a stream, not a buffered response, and a caller who knows better
  raises the ceiling per client with `configure(max_body_bytes=...)`.
- Memory is not the constraint at 16 MiB (≈25 MiB resident delta, 1.5–2× the
  body), but the resident delta at 32 MiB and above (83–175 MiB) is a second
  reason not to buffer there by default.

## The finding that changed the design

The manager forwards `Authorization` and `Cookie` to a different origin when
it follows a redirect itself. decision-4 forbids forwarding credentials across
unrelated redirect origins, so the transport cannot delegate redirects to Qt:
`NativeNetworkTransport` sets `ManualRedirectPolicy` on every hop, resolves
`Location` itself, drops `Authorization`, `Cookie`, `Proxy-Authorization` and
the QGIS `auth_config` when scheme, host or port changes, refuses `https` →
`http` and non-HTTP schemes, rewrites `303` (and `301`/`302` after `POST`) to
`GET` without the body, and counts hops against `max_redirects`. The 0.7 ms per
hop this costs is the price of the rule.
`tests/test_network_native.py` pins the dropped headers against two loopback
origins.

## What this does NOT qualify

- Real latency: every hop and every byte here is loopback. The redirect limit
  is a safety stop, not a latency budget; on a slow link twenty hops take as
  long as they take, and the per-request timeout is what bounds them.
- macOS and Windows numbers, or a Desktop GUI with a display: the harness
  drives Qt with `processEvents()` the way the scheduler spike did.
- Streaming or chunked downloads: a body over the ceiling is aborted while
  downloading, which is the intended behaviour, not a measured path.
