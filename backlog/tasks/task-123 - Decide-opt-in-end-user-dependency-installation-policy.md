---
id: TASK-123
title: Decide opt-in end-user dependency installation policy
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
updated_date: '2026-10-28 15:59'
labels: []
dependencies: []
priority: medium
type: spike
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner wants an easy end-user approval prompt for missing third-party packages such as pandas, using QGIS-compatible Python and pip. This conflicts with decision-50 and TASK-77, which currently forbid SDK installation and only probe externals. No installer or change in policy is approved or implemented; no release target is selected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Resolve and record whether policy changes are acceptable before implementation; compare externally managed/PEP 668 environments, OSGeo4W, QGIS bundles, user-site or isolated environments and host-specific fallbacks without assuming pip exists.
- [ ] #2 Specify explicit informed approval, showing packages, versions, destination and risks, off-GUI execution, cancellation/failure/retry, re-probe and restart; never perform an unattended or silent install, including during startup.
- [ ] #3 Assess supply-chain trust, compiled wheels and ABI, shared interpreter and already-loaded modules, privilege boundaries and safe rollback; preserve manual provisioning and TASK-77 behavior until a new decision is accepted.
<!-- AC:END -->
