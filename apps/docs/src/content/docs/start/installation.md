---
title: Install the QGIS SDK
description: Install the qgis-sdk developer kit from PyPI or prefix.dev, the TypeScript SDK from npm, and check what the command finds on this machine - two minutes.
sidebar:
  order: 1
---

The Python developer kit `qgis-sdk` installs two packages at matching
versions: `qgis-sdk-runtime`, what a plugin imports inside QGIS, and
`qgis-sdk-tools`, the `qgis-sdk` command. Neither installs anything into a
QGIS: a built plugin vendors its own copy of the runtime.

## Which Python?

The tools run on any Python 3.11+ - a virtual environment, Pixi, the system
interpreter. `qgis-sdk test --target qgis`, `qgis-sdk dev` and `qgis-sdk build`
find a QGIS through `QGIS_PREFIX_PATH`, `qgis` on `PATH`, the current
environment, or `[tool.qgis-sdk] qgis-prefix` in the project.

## How do I install the Python kit?

With pip, into any environment:

```sh
pip install qgis-sdk
# with the optional Pydantic controlled-deployment adapter:
pip install "qgis-sdk[controlled-deployment]"
```

With Pixi, from the prefix.dev channel:

```sh
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

The runtime alone, for the QGIS Python console, a host script or a copy to
vendor:

```sh
pip install qgis-sdk-runtime
```

## How do I install the TypeScript SDK?

Only a plugin with a web page needs it; `qgis-sdk new --web` writes the
dependency for you.

```sh
bun add @archont561/qgis-sdk        # or its unscoped alias: bun add qgis-sdk
bun add @archont561/qgis-sdk-ui     # the web components, optional
```

```sh
npm install @archont561/qgis-sdk     # or: npm install qgis-sdk
npm install @archont561/qgis-sdk-ui  # the web components, optional
```

## Did it work?

```sh
qgis-sdk --help
qgis-sdk targets      # the support matrix, and where this host stands in it
```

`targets` prints the QGIS and Python versions the kit is qualified against
and which of them this machine can reach, so you know up front whether the
native test layers and `dev` will run here or only the QGIS-free ones.

## Where next

- [Your first plugin](/qgis-sdk/start/first-plugin/) - scaffold, check, test,
  run inside QGIS, build the ZIP.
- [Supported targets](/qgis-sdk/python/supported-targets/) - the full matrix
  and the qualification behind it.
