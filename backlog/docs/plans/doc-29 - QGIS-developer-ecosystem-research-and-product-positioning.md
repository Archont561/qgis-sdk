---
id: doc-29
title: QGIS developer ecosystem research and product positioning
type: other
created_date: '2026-10-28 16:24'
---

# QGIS developer ecosystem research and product positioning

The owner positions QGIS SDK as **the next-generation SDK for effortless QGIS
plugin authoring**. Its practical promise is less boilerplate: declare Python
actions, test logic without QGIS, use the same actions in native and web
interfaces, and build a plugin with a private SDK runtime. This is a product
positioning, not a guarantee that all plugin development is effortless.

## Current strengths and qualifications

The reference plugin `examples/simple` demonstrates one declared action
behind native and web interfaces, with a generated typed TypeScript bridge.
The SDK also offers pure, QGIS and Desktop test targets, an isolated source
development profile, a build that vendors the runtime privately, and scoped
lifecycle management. Framework-free, React, Vue and Svelte bindings exist;
scaffold and qualification support differs. The kit remains experimental 0.x;
Windows and macOS native QGIS are not qualified in the current support matrix.
Fakes and source lint do not prove native correctness or security. In
particular, TASK-118 and TASK-119 record unresolved export and Processing
safety gaps. Worker-first jobs are planned for 0.9.0, not shipped.

## Review of developer tools (2026-10-28)

The following are ideas for independent design, not newly accepted runtime
requirements or a decision to add dependencies. Published package contents and
project descriptions were reviewed; integration with this SDK was not tested.
Do not copy third-party source or tests without license review; most tools
below are GPL-licensed, whereas the SDK is MIT-licensed.

| Project | Concepts to evaluate | Disposition |
| --- | --- | --- |
| [pytest-qgis](https://github.com/osgeosuomi/pytest-qgis) | Isolated project, Processing and layer fixtures; bounded event waits and ownership-aware teardown. | TASK-131; preserve pure/QGIS/Desktop target differences and real Desktop iface. |
| [qgis-plugin-tools](https://github.com/osgeosuomi/qgis_plugin_tools) | Job-test observations, progress/cancellation and developer diagnostics. | TASK-131 for test helpers; its runtime widgets and utilities are not developer-only. |
| [flake8-qgis](https://github.com/osgeosuomi/flake8-qgis) | QGIS/Qt migration, ignored failure results and Processing diagnostics. | TASK-132, distinct from job-specific TASK-117; avoid false positives and claims of thread safety. |
| [qgis-plugin-analyzer](https://github.com/geociencio/qgis-plugin-analyzer) | Discoverable rule catalog, scopes, exclusions, metadata and security checks. | TASK-132 and existing TASK-105; SDK diagnostics already have stable IDs and JSON. |
| [qgis-stubs](https://github.com/leonhard-s/qgis-stubs) | Version-aware IDE and type-checker support using QGIS-generated stubs. | TASK-133 spike; QGIS 4 stubs are prerelease and static typing is not native evidence. |
| [qgis-plugin-dev-tools](https://github.com/nlsfi/qgis-plugin-dev-tools) | Translation tooling discovery, deterministic translation checks and publishing an existing ZIP. | Existing TASK-103 and TASK-100; do not replace SDK build or adopt unsafe dependency path mutation. |
| [qgis-plugin-ci](https://github.com/qgis/qgis-plugin-ci) | Release preflight, prerelease handling, private repository indexes and translations. | Existing TASK-100/103; verify and publish the exact built archive, not a silently rebuilt one. |
| [qgis-plugin-manager](https://github.com/3liz/qgis-plugin-manager) | Pinned companion plugins and repositories for reproducible integration tests. | TASK-134 spike; isolated profiles, explicit trust, integrity and no end-user package installation. |
| [qgis-manage](https://github.com/geociencio/qgis-plugin-manager) | Deployment preview, built-artifact validation, safe profile selection and backups. | TASK-100 already covers publishing checks; deployment into an existing profile remains an unapproved future idea. SDK dev already loads source in an isolated profile. |

TASK-135 proposes a tested one-action narrative spanning Python, a pure test,
native UI and generated web client. New TASK-131–135 have no release assigned.
TASK-100, 103, 105, 115 and 117 retain their existing commitments and now
reference relevant research; no new product or release decision is implied.
See [doc-28](doc-28%20-%20Session-synthesis-worker-jobs-API-ergonomics-and-PyQGIS-safety.md)
for the broader session's decisions, defects and proposals.
