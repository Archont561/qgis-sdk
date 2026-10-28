---
id: doc-12
title: qgis-sdk Python package guide
type: guide
created_date: '2026-10-24 21:20'
---

# qgis-sdk Python package guide

This guide moved to [apps/docs/guides](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md). The entries below preserve historical section links; edit the new source.

## Installation

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#installation)

## Supported targets

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#supported-targets)

### What the matrix says

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-the-matrix-says)

### The bridge pair

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#the-bridge-pair)

### Where the evidence is recorded

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#where-the-evidence-is-recorded)

## Declarations

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#declarations)

### Ids and titles default from the name

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#ids-and-titles-default-from-the-name)

### What does `describe_plugin` do, and not do?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-does-describe_plugin-do-and-not-do)

### Version 1 description contract

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#version-1-description-contract)

#### Which schema subset is supported?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#which-schema-subset-is-supported)

#### What makes a valid action?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-makes-a-valid-action)

#### Defaults, nullability and unknown properties

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#defaults-nullability-and-unknown-properties)

#### What fails, and how

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-fails-and-how)

## Pure contract layer

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#pure-contract-layer)

## Scoped plugin runtime

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#scoped-plugin-runtime)

## Desktop host: `host()` and the project manifest

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#desktop-host-host-and-the-project-manifest)

## Forms: an action's inputs as a window

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#forms-an-actions-inputs-as-a-window)

## Desktop bindings and native surfaces

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#desktop-bindings-and-native-surfaces)

### Input components

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#input-components)

### Wiring: `@on`, `@subscribe`, `ctx.on`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#wiring-on-subscribe-ctxon)

### The declarative form: components as class attributes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#the-declarative-form-components-as-class-attributes)

### Containers, feedback, buttons and `Custom`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#containers-feedback-buttons-and-custom)

### Behaviour mixins

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#behaviour-mixins)

### Designer files and the pure-PyQt path

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#designer-files-and-the-pure-pyqt-path)

### Testing surfaces without QGIS: `build_surface`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#testing-surfaces-without-qgis-build_surface)

### `ctx.log`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#ctxlog)

### `ctx.notifications`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#ctxnotifications)

### `ctx.files`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#ctxfiles)

## Processing algorithms and safe outputs

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#processing-algorithms-and-safe-outputs)

### How do I run one from a context?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#how-do-i-run-one-from-a-context)

### What does the description carry?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-does-the-description-carry)

### Safe outputs

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#safe-outputs)

#### Non-destructive by construction (decision-19)

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#non-destructive-by-construction-decision-19)

#### Explicit CRS and units where a distance is involved

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#explicit-crs-and-units-where-a-distance-is-involved)

### Any registered algorithm: `list`, `describe`, `run` and the generated registry

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#any-registered-algorithm-list-describe-run-and-the-generated-registry)

#### The generated modules

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#the-generated-modules)

#### Over the fakes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#over-the-fakes)

#### Generating modules for another provider

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#generating-modules-for-another-provider)

## Providers: algorithms in the QGIS Processing toolbox

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#providers-algorithms-in-the-qgis-processing-toolbox)

## WebEngine bridge, host side

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#webengine-bridge-host-side)

### Generated TypeScript schema module

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#generated-typescript-schema-module)

### Host surface

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#host-surface)

## Networking

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#networking)

### How does a request run?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#how-does-a-request-run)

#### Coroutines, scheduled by the host

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#coroutines-scheduled-by-the-host)

#### Blocking is explicit and off the GUI thread

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#blocking-is-explicit-and-off-the-gui-thread)

#### Derived, immutable clients

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#derived-immutable-clients)

### What comes back?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-comes-back)

#### One `Response`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#one-response)

#### Errors you can tell apart by `code`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#errors-you-can-tell-apart-by-code)

### Which limits and configuration apply?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#which-limits-and-configuration-apply)

#### Defaults from measurement

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#defaults-from-measurement)

#### QGIS owns the configuration

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#qgis-owns-the-configuration)

#### Redirects are followed by the transport, not by Qt

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#redirects-are-followed-by-the-transport-not-by-qt)

### What builds on it?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-builds-on-it)

#### Typed services compose over it

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#typed-services-compose-over-it)

#### Tests inject a fake

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#tests-inject-a-fake)

## Scoped jobs

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#scoped-jobs)

### What is checked before a job runs?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#what-is-checked-before-a-job-runs)

### Migrating from the 0.5 class form

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#migrating-from-the-05-class-form)

### Three rules decide everything else

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#three-rules-decide-everything-else)

#### A request is not a state

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#a-request-is-not-a-state)

#### Callbacks run on the tick, never on a worker

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#callbacks-run-on-the-tick-never-on-a-worker)

#### Disposal beats delivery

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#disposal-beats-delivery)

### How do hosts compose the service?

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#how-do-hosts-compose-the-service)

## Project scaffold

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#project-scaffold)

### Choosing Desktop or standalone Qt mode

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#choosing-desktop-or-standalone-qt-mode)

### Processing starter: `--algorithm`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#processing-starter---algorithm)

### Native UI starter: `--ui native`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#native-ui-starter---ui-native)

### Web UI: vanilla or React, dialog or dock

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#web-ui-vanilla-or-react-dialog-or-dock)

## Project checks

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#project-checks)

## Running tests: `qgis-sdk test`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#running-tests-qgis-sdk-test)

## Developing against QGIS: `qgis-sdk dev`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#developing-against-qgis-qgis-sdk-dev)

## Building an installable ZIP: `qgis-sdk build`

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#building-an-installable-zip-qgis-sdk-build)

### CLI runtime

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#cli-runtime)

## Optional controlled-deployment adapter

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#optional-controlled-deployment-adapter)

## 0.1.0 experimental release and migration policy

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#010-experimental-release-and-migration-policy)

## 0.2.0 migration notes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#020-migration-notes)

## 0.3.0 migration notes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#030-migration-notes)

## 0.7.0 migration notes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#070-migration-notes)

## 0.6.0 migration notes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#060-migration-notes)

## 0.5.0 migration notes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#050-migration-notes)

## 0.4.0 migration notes

[Open this section](../../../apps/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md#040-migration-notes)
