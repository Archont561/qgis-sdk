---
id: decision-5
title: Rust algorithm implementations are post-v1 and backend-neutral
date: '2026-10-15 23:05'
status: proposed
---
## Context

Rust may be useful for CPU-intensive processing, but coupling the first SDK release to a native extension would add platform, Python ABI, QGIS-version, build, and distribution complexity. Plugin declarations and Processing integration should remain usable without a native toolchain.

## Decision

Proposed: keep v1 algorithms declared and adapted to QGIS Processing in Python. Consider an optional Rust compute backend only after v1 and only for measured workloads. Keep QGIS/Qt object access, layer lifecycle, and Processing integration in Python; pass plain, typed, batch-oriented data across a backend boundary. The Python implementation remains a fallback/reference and defines the observable contract.

## Consequences

- No Rust runtime dependency is required for v1 plugins.
- The algorithm contract should avoid exposing QGIS objects to a future native backend.
- A later proposal must include representative benchmarks, parity tests, cancellation/progress behavior, and a platform/Python ABI packaging plan.
- This is a roadmap direction, not a commitment to build or ship Rust support.