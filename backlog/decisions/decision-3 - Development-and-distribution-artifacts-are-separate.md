---
id: decision-3
title: Development and distribution artifacts are separate
date: '2026-10-15 23:05'
status: accepted
---
## Context

The developer SDK and the QGIS-installed plugin have different consumers and runtime needs. The user explicitly confirmed plugin-private bundling and a pure-Python-first dependency policy on 2026-10-16. This replaces the earlier provisional distribution wording; it does not prove packaging is implemented.

## Decision

Distribute qgis-sdk as developer tooling. qgis-sdk build produces a QGIS-installable ZIP with one plugin root, required plugin-private SDK runtime modules, metadata, declared resources and production web assets. End users install the plugin ZIP without separately installing the SDK runtime or developer tooling. Do not create a separate required shared qgis-sdk-runtime installation for v1.

Bundle reviewed pure-Python runtime dependencies first. Reject unsupported/undeclared dependencies and incompatible native artifacts with actionable diagnostics; do not claim general native-wheel vendoring. Never install dependencies at plugin startup. If the validation spike selects a mandatory native dependency, explicitly revisit this policy before acceptance rather than silently violating it.

Build reruns shared source checks, generates adapters/assets in staging and validates paths/layout/runtime contents. Exclude QGIS/Qt, tests/fixtures, CLI, environments, caches, secrets and unbuilt development assets. Include licenses/notices. Plugin-private imports and a two-plugin different-SDK-version test must guard collisions. Prefer explicit runtime components over speculative Python tree shaking and aim for deterministic artifacts.

Do not implicitly run the behavior suite, publish or install into a user's profile. Requested real-QGIS installation/startup verification is separate and must fail clearly if its required runtime is unavailable. A valid ZIP alone is not proof of behavior.

## Consequences

- Qualification must use clean target environments and include dependency/license checks.
- Pure-Python-first packaging and deferred Rust reduce initial native distribution scope, not the need to test host-provided QGIS/Qt compatibility.
- Binary dependencies, separate runtime products and multi-platform native ZIP strategies require a later explicit decision.

## Confirmed dependency setup policy (2026-10-16)

Keep automatic dependency installation out of the initial SDK release. Ordinary
plugin installation uses the plugin ZIP with reviewed, qualified pure-Python
runtime dependencies bundled privately. A startup consent dialog does not remove
the risks of modifying QGIS's shared Python environment; do not make pip or network
access a prerequisite for ordinary plugin startup.

If a required dependency is missing or incompatible, a minimal bootstrap should
report an actionable diagnostic and leave the plugin safely inactive. The bootstrap
must not first import the dependency-dependent runtime. Provide manual setup
instructions where appropriate; this is a requirement, not an implemented feature.

Controlled/internal deployments may use explicitly provisioned native dependencies
in a supported QGIS Python or Conda environment. This is not permission to make a
native validator mandatory for ordinary plugin distribution. Any such selection
still requires an explicit policy review and target qualification. pip provisioning
must target the actual supported QGIS interpreter/environment, not a generic system
pip or an assumed `sys.executable`; keep Conda-managed provisioning distinct from
pip modification of a Desktop installation. Successful installation alone does not
prove native imports or plugin behavior work in QGIS.

A one-click dependency setup action is deferred, optional future work, not an
initial-release requirement or a selected implementation. If later approved, prefer
an explicit **Set up dependencies…** action over automatic startup installation.
It would need informed consent, a qualified interpreter launch path, pinned binary
artifacts, a non-blocking installer subprocess, staged installation into a
plugin-managed destination, conflict detection, cancellation/recovery, manual/offline
alternatives and restart handling. A private directory is not full in-process
isolation: QGIS plugins share Python imports and may load conflicting native
libraries. Do not silently upgrade shared packages or elevate privileges.

Validate the request backend first; do not build a dependency installer as a
prerequisite for selecting it. Bundled pure-Python dependencies still require
license, import-collision and real-QGIS qualification.
