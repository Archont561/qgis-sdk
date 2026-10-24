#!/usr/bin/env bash
# Devcontainer setup for the QGIS SDK workspace, kept outside JSON so setup steps stay readable.
set -euo pipefail

pixi --version

# CLI tooling the pixi image does not ship with.
pixi global install git gh

# The pixi-sandbox CLI, from the Archont561 channel on prefix.dev.
pixi global install --channel https://prefix.dev/archont561/archont561 --channel conda-forge pixi-sandbox

# The project's own environment, pinned to the lockfile.
pixi install --locked
