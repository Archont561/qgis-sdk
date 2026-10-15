---
id: m-4
title: "Post-1.0 — Optional Rust algorithm backend"
---

## Description

Explore Rust only after v1, for measured CPU-bound workloads, behind a stable Python-facing algorithm/Processing contract. This milestone is optional and does not make Rust part of the v1 runtime.

## Exit criteria

- A specific workload has benchmark evidence that justifies native acceleration.
- The Python implementation remains a reference/fallback with behavioral parity tests.
- Native code receives plain typed/batch data; QGIS/Qt objects remain owned by Python.
- Cancellation, progress, ABI/platform wheels, and plugin ZIP behavior are demonstrated before shipping.
