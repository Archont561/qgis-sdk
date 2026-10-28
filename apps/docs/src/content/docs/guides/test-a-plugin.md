---
title: Test and run a plugin
description: Scaffold a plugin, exercise it without QGIS, then opt into QGIS and Desktop checks.
sidebar:
  order: 1
---

Start with the [installed developer kit](/qgis-sdk/start/installation/). The
QGIS-free tests run on the SDK fakes; they are not a substitute for running a
plugin inside QGIS.

## Create and check the project

```sh
qgis-sdk new field_tools --no-input
cd field_tools
qgis-sdk check
```

`check` reports project and declaration problems before QGIS loads the plugin.
See [project checks](/qgis-sdk/python/project-checks/) for the rule IDs and
remedies.

## Test without QGIS

```sh
qgis-sdk test
```

Add tests under `tests/` for the plugin's actions and services. The fakes
exercise plugin behavior without starting QGIS; see the
[scoped plugin runtime](/qgis-sdk/python/scoped-plugin-runtime/) for the
service boundary.

## Qualify on a QGIS host

With a supported QGIS installation available, run:

```sh
qgis-sdk targets
qgis-sdk test --target qgis
qgis-sdk dev
```

`targets` reports what the machine can reach. The QGIS target adds native
checks; `dev` starts QGIS Desktop with the plugin loaded from source and
reloads on save. Desktop requires a working display and QGIS installation.
See [supported targets](/qgis-sdk/python/supported-targets/) and
[developing against QGIS](/qgis-sdk/python/developing-against-qgis-qgis-sdk-dev/)
for discovery and options.

## Build for distribution

```sh
qgis-sdk build
```

Install the ZIP in `dist/` through QGIS's plugin manager. See the
[build reference](/qgis-sdk/python/building-an-installable-zip-qgis-sdk-build/)
for packaging details.
