---
id: doc-13
title: qgis-sdk TypeScript package guide
type: guide
created_date: '2026-10-24 21:20'
---

# qgis-sdk TypeScript package guide

This guide moved to [apps/docs/guides](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md). The entries below preserve historical section links; edit the new source.

## Installation

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#installation)

## Exports

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#exports)

### Which entry for which page

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#which-entry-for-which-page)

## Transport client

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#transport-client)

### Creating a client

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#creating-a-client)

### What the client guarantees

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#what-the-client-guarantees)

### Correlated calls

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#correlated-calls)

### Three different outcomes

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#three-different-outcomes)

### Subscriptions

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#subscriptions)

## Host namespaces

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#host-namespaces)

### Processing from a page: `algorithms.*` and `runAlgorithm`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#processing-from-a-page-algorithms-and-runalgorithm)

## The schema module and `QgisSdk`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#the-schema-module-and-qgissdk)

### What does the module export?

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#what-does-the-module-export)

### How does a page build a `QgisSdk`?

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#how-does-a-page-build-a-qgissdk)

### How does it connect, and what does it check?

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#how-does-it-connect-and-what-does-it-check)

#### Transport

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#transport)

#### Compile time

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#compile-time)

#### Runtime

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#runtime)

#### Streams are operations too (decision-28)

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#streams-are-operations-too-decision-28)

### What else is on the instance?

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#what-else-is-on-the-instance)

#### `qgis.host`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#qgishost)

#### `qgis.ready`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#qgisready)

#### Owned by CI

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#owned-by-ci)

### The 0.3.0 generated client

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#the-030-generated-client)

## Stores: the framework-free core

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#stores-the-framework-free-core)

### Using the stores

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#using-the-stores)

### The four stores

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#the-four-stores)

### `OperationStore(operation)`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#operationstoreoperation)

### `StreamStore(open, handlers?)`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#streamstoreopen-handlers)

### `FormStore` / `formStore(qgis, actionId, { initial })`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#formstore--formstoreqgis-actionid--initial-)

### `HostQueryStore(qgis, hostOperationId, loader)`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#hostquerystoreqgis-hostoperationid-loader)

### Misuse, and the shared behaviour suite

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#misuse-and-the-shared-behaviour-suite)

## React bindings

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#react-bindings)

## Vue bindings

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#vue-bindings)

## Svelte bindings

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#svelte-bindings)

## Components: `@archont561/qgis-sdk-ui`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#components-archont561qgis-sdk-ui)

### The elements

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#the-elements)

#### The keyword forms, both spellings

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#the-keyword-forms-both-spellings)

### Styling: `style.css`, the tokens and `./uno`

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#styling-stylecss-the-tokens-and-uno)

### Wrappers

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#wrappers)

### Storybook and the stories as fixtures

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#storybook-and-the-stories-as-fixtures)

## Testing against a scripted host

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#testing-against-a-scripted-host)

## 0.5.0 migration notes

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#050-migration-notes)

## 0.2.0 migration notes

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#020-migration-notes)

## 0.3.0 migration notes

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#030-migration-notes)

## 0.4.0 migration notes

[Open this section](../../../apps/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#040-migration-notes)
