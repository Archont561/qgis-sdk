---
id: decision-5
title: Rust algorithm implementations are post-v1 and backend-neutral
date: '2026-10-15 23:05'
status: accepted
---
## Context

Earlier discussion considered both author-written Rust extensions and SDK-owned acceleration. The 2026-10-16 clarification explicitly selected deferring Rust shipping for v1, rather than making either option a release prerequisite.

## Decision

Keep v1 algorithm authoring and QGIS Processing integration in Python. Do not ship SDK-owned Rust compute or first-class custom Rust scaffolding/build integration in v1. Plugin authors and end users need no SDK-imposed Cargo, Rust compiler, PyO3 or maturin setup. Prefer existing QGIS/native capabilities and measured workflows.

If compute services are justified, expose narrow typed implementation-neutral operations with explicit batching, errors, CRS/units, thread/cancellation and output semantics. Do not create a mandatory qgis-sdk-algorithms crate or a generic backend framework in anticipation of future Rust.

Future SDK-owned acceleration and future author-written native extensions are separate proposals. Evaluate actual speedup including data conversion, supported QGIS/Python/platform artifacts, plugin-private bundling, licensing, crash behavior and cancellation. Where equivalent Python/reference behavior exists, test parity; do not promise a fallback for every operation or silently mask native execution failures. Keep QGIS/Qt objects and lifecycle in Python and exchange plain typed/batched data across any future native boundary.

## Consequences

- No Rust shipping/toolchain requirement is part of the confirmed v1 slice.
- A later opt-in authoring workflow could use ordinary PyO3 and maturin/Cargo, but is not a supported SDK command today.
- SDK-owned native acceleration would transfer compilation/distribution responsibility to SDK maintainers, not eliminate it.
